import pandas as pd
import json
import os
import csv
from logger_setup import setup_logs

# Define a separate state file and a new CSV log file
STATE_FILE = 'logs/stat_arb_state.json'
TRADE_LOG_FILE = 'logs/stat_arb_trades.csv'
event_logger, _ = setup_logs()

class StatArbPortfolio:
    def __init__(self, initial_capital=100000.0, commission_pct=0.001):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.commission_pct = commission_pct
        self.positions = {} # e.g., {'BTCUSDT': {'quantity': 1, 'entry_price': 50000}, 'ETHUSDT': ...}
        self.save_state()
        self._initialize_trade_log()

    def _initialize_trade_log(self):
        """Creates the CSV log file with headers if it doesn't exist."""
        if not os.path.exists(TRADE_LOG_FILE):
            if not os.path.exists('logs'):
                os.makedirs('logs')
            with open(TRADE_LOG_FILE, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'exit_timestamp', 'asset_1', 'asset_2', 'direction',
                    'entry_price_1', 'exit_price_1', 'quantity_1',
                    'entry_price_2', 'exit_price_2', 'quantity_2',
                    'gross_pnl', 'net_pnl'
                ])

    def _log_trade_to_csv(self, trade_details):
        """Appends a completed trade to the CSV log file."""
        with open(TRADE_LOG_FILE, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                trade_details.get('exit_timestamp'),
                trade_details.get('asset_1'),
                trade_details.get('asset_2'),
                trade_details.get('direction'),
                trade_details.get('entry_price_1'),
                trade_details.get('exit_price_1'),
                trade_details.get('quantity_1'),
                trade_details.get('entry_price_2'),
                trade_details.get('exit_price_2'),
                trade_details.get('quantity_2'),
                f"{trade_details.get('gross_pnl'):.2f}",
                f"{trade_details.get('net_pnl'):.2f}"
            ])

    def update_position(self, symbol, quantity, price):
        """Updates or creates a position."""
        self.positions[symbol] = {'quantity': quantity, 'entry_price': price}
        event_logger.info(f"Position opened/updated: {symbol}, Qty: {quantity}, Price: {price}")
        self.save_state()

    def close_pair_trade(self, asset1, price1, asset2, price2, direction):
        """Closes a pair trade, calculates P&L, and logs it."""
        if asset1 not in self.positions or asset2 not in self.positions:
            event_logger.warning("Attempted to close a pair trade but positions not found.")
            return

        pos1 = self.positions[asset1]
        pos2 = self.positions[asset2]

        # Calculate P&L for each leg
        pnl1 = (price1 - pos1['entry_price']) * pos1['quantity']
        pnl2 = (price2 - pos2['entry_price']) * pos2['quantity']
        gross_pnl = pnl1 + pnl2

        # Calculate commission
        commission1 = abs(pos1['quantity'] * price1 * self.commission_pct)
        commission2 = abs(pos2['quantity'] * price2 * self.commission_pct)
        total_commission = commission1 + commission2

        net_pnl = gross_pnl - total_commission

        trade_details = {
            'exit_timestamp': pd.Timestamp.now(tz='America/New_York').isoformat(),
            'asset_1': asset1,
            'asset_2': asset2,
            'direction': direction,
            'entry_price_1': pos1['entry_price'], 'exit_price_1': price1, 'quantity_1': pos1['quantity'],
            'entry_price_2': pos2['entry_price'], 'exit_price_2': price2, 'quantity_2': pos2['quantity'],
            'gross_pnl': gross_pnl,
            'net_pnl': net_pnl
        }

        self._log_trade_to_csv(trade_details)
        event_logger.info(f"Pair trade closed. Net P&L: {net_pnl:.2f}")

        # Clear positions
        self.positions.clear()
        self.current_capital += net_pnl
        self.save_state()

    def save_state(self):
        """Saves the current state to a JSON file."""
        try:
            if not os.path.exists('logs'):
                os.makedirs('logs')
            state_to_save = {
                "initial_capital": self.initial_capital,
                "current_capital": self.current_capital,
                "positions": self.positions,
            }
            with open(STATE_FILE, 'w') as f:
                json.dump(state_to_save, f, indent=4)
        except Exception as e:
            event_logger.error(f"Failed to save state for stat arb bot: {e}")

    @classmethod
    def load_state(cls):
        """Loads portfolio state from its dedicated file."""
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r') as f:
                    state = json.load(f)
                p = cls(initial_capital=state.get('initial_capital', 100000.0))
                p.current_capital = state.get('current_capital', 100000.0)
                p.positions = state.get('positions', {})
                return p
            except Exception as e:
                event_logger.error(f"Error decoding stat_arb_state.json: {e}. Creating new state.")
                return cls()
        else:
            return cls()