import json
import logging
import os
import pandas as pd
import numpy as np
from logger_setup import append_to_csv

# Get the absolute path of the directory where this file is located
_current_dir = os.path.dirname(os.path.abspath(__file__))
_log_dir = os.path.join(_current_dir, 'logs')

class Portfolio:
    def __init__(self, initial_capital, risk_per_trade_percent, commission_per_trade, slippage_cost_per_contract, state_file_path='logs/strategy_state.json'):
        self.state_file = os.path.join(_current_dir, os.path.basename(state_file_path))
        log_dir_for_file = os.path.dirname(self.state_file)
        if not os.path.exists(log_dir_for_file):
            try:
                os.makedirs(log_dir_for_file)
            except Exception as e:
                logging.critical(f"FATAL: Could not create log directory. ERROR: {e}")
                raise

        self.trade_log_file = os.path.join(log_dir_for_file, 'trade_log.csv')
        self.initial_capital = initial_capital
        self.risk_per_trade_percent = risk_per_trade_percent
        self.commission_per_trade = commission_per_trade
        self.slippage_cost_per_contract = slippage_cost_per_contract

        loaded_state = self._load_state()
        self.state = loaded_state if loaded_state is not None else self._create_initial_state()

        self._setup_trade_log()
        logging.info("Portfolio instance created.")

    @classmethod
    def load_state_from_file(cls):
        instance = cls(100000, 0.015, 1.0, 0.5)
        return instance

    def get_dashboard_data(self):
        # This method is now correct and remains unchanged from the last version
        if not self.state:
            return {"net_pnl": 0.0, "sharpe_ratio": 0.0, "max_drawdown": 0.0, "win_rate": 0.0, "total_trades": 0, "profit_factor": 0.0, "open_position": "State file not found. Waiting for bot.", "equity_curve": []}
        open_pos_str = "System is currently flat."
        if self.state.get('position'):
            pos = self.state['position']
            open_pos_str = f"{pos.get('direction', 'N/A').upper()} {pos.get('contracts', 0):.2f} of {pos.get('symbol', 'N/A')} from {pos.get('entry_price', 0):.2f}"
        closed_trades = self.state.get('closed_trades', [])
        if not closed_trades:
            return {"net_pnl": 0.0, "sharpe_ratio": 0.0, "max_drawdown": 0.0, "win_rate": 0.0, "total_trades": 0, "profit_factor": 0.0, "open_position": open_pos_str, "equity_curve": self.state.get('equity_history', [])}
        trade_pnls = [t['net_pnl'] for t in closed_trades]
        net_pnl = sum(trade_pnls)
        total_trades = len(closed_trades)
        winning_trades = [p for p in trade_pnls if p > 0]
        win_rate = (len(winning_trades) / total_trades) * 100 if total_trades > 0 else 0.0
        total_profit = sum(winning_trades)
        total_loss = abs(sum(p for p in trade_pnls if p < 0))
        profit_factor = total_profit / total_loss if total_loss > 0 else 0.0
        equity_curve_df = pd.DataFrame(self.state.get('equity_history', []))
        max_drawdown = 0.0
        if not equity_curve_df.empty and 'equity' in equity_curve_df.columns:
            equity_curve_df['equity'] = pd.to_numeric(equity_curve_df['equity'])
            peak = equity_curve_df['equity'].expanding(min_periods=1).max()
            drawdown = (equity_curve_df['equity'] - peak) / peak
            if not drawdown.empty:
                max_drawdown = abs(drawdown.min() * 100)
        sharpe_ratio = 0.0
        return {"net_pnl": net_pnl, "sharpe_ratio": sharpe_ratio, "max_drawdown": max_drawdown, "win_rate": win_rate, "total_trades": total_trades, "profit_factor": profit_factor, "open_position": open_pos_str, "equity_curve": self.state.get('equity_history', [])}

    def _load_state(self):
        try:
            with open(self.state_file, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            logging.warning(f"State file not found or is invalid: {self.state_file}")
            return None

    def _save_state(self):
        try:
            with open(self.state_file, 'w') as f:
                json.dump(self.state, f, indent=4, default=str)
        except Exception as e:
            logging.critical(f"CRITICAL ERROR: Could not save portfolio state to {self.state_file}. Reason: {e}")

    def _create_initial_state(self):
        """
        MODIFIED: This method now only creates the state in memory.
        It does NOT save the file immediately, preventing the startup write error.
        The file will be created on the first actual event (like an exit_position).
        """
        logging.info("Creating a new initial portfolio state in memory.")
        state = {
            "initial_capital": self.initial_capital, "current_capital": self.initial_capital,
            "position": None, "closed_trades": [],
            "equity_history": [{"timestamp": pd.Timestamp.now(tz='America/New_York').isoformat(), "equity": self.initial_capital}]
        }
        return state

    def _setup_trade_log(self):
        try:
            if not os.path.exists(self.trade_log_file):
                pd.DataFrame(columns=['timestamp', 'direction', 'contracts', 'entry_price', 'exit_price', 'net_pnl', 'exit_reason']).to_csv(self.trade_log_file, index=False)
        except Exception as e:
            logging.critical(f"CRITICAL ERROR: Could not create trade log file at {self.trade_log_file}. Reason: {e}")

    def _log_trade(self, trade_data):
        append_to_csv(self.trade_log_file, trade_data)

    def is_position_open(self):
        return self.state and self.state.get('position') is not None

    def enter_position(self, direction, symbol, entry_price):
        if self.is_position_open():
            logging.warning("Signal to enter position received, but a position is already open.")
            return
        capital_at_risk = self.state['current_capital'] * self.risk_per_trade_percent
        contracts = (capital_at_risk / (entry_price * 0.01)) if entry_price > 0 else 0
        logging.info(f"ENTERING {direction.upper()}: {contracts:.2f} contracts at {entry_price:.2f}")
        self.state['position'] = {"symbol": symbol, "direction": direction, "entry_price": entry_price, "contracts": contracts, "entry_timestamp": pd.Timestamp.now(tz='America/New_York').isoformat()}
        self._save_state()

    def exit_position(self, exit_price, reason):
        if not self.is_position_open():
            logging.warning("Signal to exit position received, but no position is open.")
            return
        position = self.state['position']
        pnl_direction = 1 if position['direction'] == 'long' else -1
        gross_pnl = (exit_price - position['entry_price']) * position['contracts'] * pnl_direction
        net_pnl = gross_pnl - self.commission_per_trade
        logging.info(f"EXITING {position['direction'].upper()} at {exit_price:.2f}. Reason: {reason}. P&L: {net_pnl:.2f}")
        self.state['current_capital'] += net_pnl
        self.state['equity_history'].append({"timestamp": pd.Timestamp.now(tz='America/New_York').isoformat(), "equity": self.state['current_capital']})
        trade_log_entry = {"timestamp": pd.Timestamp.now(tz='America/New_York').isoformat(), "direction": position['direction'], "contracts": position['contracts'], "entry_price": position['entry_price'], "exit_price": exit_price, "net_pnl": net__pnl, "exit_reason": reason}
        self.state['closed_trades'].append(trade_log_entry)
        self.state['position'] = None
        self._log_trade(trade_log_entry)
        self._save_state()