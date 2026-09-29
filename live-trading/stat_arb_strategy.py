import pandas as pd
import numpy as np
import json
from statsmodels.tsa.stattools import adfuller
import statsmodels.api as sm
from logger_setup import setup_logs

event_logger, _ = setup_logs()

class StatisticalArbitrageStrategy:
    def __init__(self, portfolio_manager, data_handler):
        self.portfolio = portfolio_manager
        self.data_handler = data_handler
        self._load_parameters()

        self.hedge_ratio = None
        self.spread_mean = None
        self.spread_std = None
        self.is_cointegrated = False
        self.trading_halted = False # NEW: Flag to halt trading

    def _load_parameters(self):
        with open('config_stat_arb.json', 'r') as f:
            self.params = json.load(f)

    def assess_and_update(self):
        event_logger.info("Re-assessing cointegration relationship...")

        pair_df = self.data_handler.fetch_pair_data(
            self.params['ASSET_1'], self.params['ASSET_2'], self.params['LOOKBACK_PERIOD_HOURS']
        )
        if pair_df is None or len(pair_df) < 100:
            event_logger.warning("Not enough historical data to assess cointegration. Halting trading.")
            self.is_cointegrated = False
            self.trading_halted = True # Halt trading if data is insufficient
            return

        asset1_prices = pair_df[self.params['ASSET_1']]
        asset2_prices = pair_df[self.params['ASSET_2']]

        asset2_prices_with_const = sm.add_constant(asset2_prices)
        model = sm.OLS(asset1_prices, asset2_prices_with_const).fit()
        spread = asset1_prices - model.predict(asset2_prices_with_const)

        p_value = adfuller(spread, maxlag=1)[1]

        if p_value < self.params['COINTEGRATION_TEST_P_VALUE_THRESHOLD']:
            self.is_cointegrated = True
            self.trading_halted = False # Resume trading if cointegrated again
            self.hedge_ratio = model.params[1]
            self.spread_mean = np.mean(spread)
            self.spread_std = np.std(spread)
            event_logger.info(f"Assets are cointegrated (p-value: {p_value:.4f}). Trading enabled.")
        else:
            self.is_cointegrated = False
            self.trading_halted = True # Halt trading if no longer cointegrated
            event_logger.warning(f"Assets are NOT cointegrated (p-value: {p_value:.4f}). Halting trading.")

    def on_bar(self):
        if not self.is_cointegrated or self.trading_halted:
            if self.trading_halted:
                event_logger.info("Trading is currently halted due to stop-loss or failed cointegration test.")
            return

        live_data = self.data_handler.fetch_pair_data(self.params['ASSET_1'], self.params['ASSET_2'], hours=1)
        if live_data is None or live_data.empty: return

        latest_prices = live_data.iloc[-1]
        price1 = latest_prices[self.params['ASSET_1']]
        price2 = latest_prices[self.params['ASSET_2']]

        current_spread = price1 - (self.hedge_ratio * price2)
        z_score = (current_spread - self.spread_mean) / self.spread_std
        event_logger.info(f"Live Z-score: {z_score:.2f}")

        entry_thresh = self.params['Z_SCORE_ENTRY_THRESHOLD']
        exit_thresh = self.params['Z_SCORE_EXIT_THRESHOLD']
        stop_thresh = self.params['Z_SCORE_STOP_LOSS_THRESHOLD']

        asset1, asset2 = self.params['ASSET_1'], self.params['ASSET_2']

        if not self.portfolio.positions:
            if z_score > entry_thresh:
                event_logger.info(f"Z-score > {entry_thresh}. SHORTING SPREAD.")
                self.portfolio.update_position(asset1, -1, price1)
                self.portfolio.update_position(asset2, self.hedge_ratio, price2)
            elif z_score < -entry_thresh:
                event_logger.info(f"Z-score < {-entry_thresh}. LONGING SPREAD.")
                self.portfolio.update_position(asset1, 1, price1)
                self.portfolio.update_position(asset2, -self.hedge_ratio, price2)
        else:
            is_long_spread = self.portfolio.positions.get(asset1, {}).get('quantity', 0) > 0
            direction = "LONG_SPREAD" if is_long_spread else "SHORT_SPREAD"

            if (is_long_spread and z_score > -exit_thresh) or (not is_long_spread and z_score < exit_thresh):
                event_logger.info(f"Closing {direction} position (mean reversion).")
                self.portfolio.close_pair_trade(asset1, price1, asset2, price2, direction)
            elif (is_long_spread and z_score < -stop_thresh) or (not is_long_spread and z_score > stop_thresh):
                event_logger.warning(f"STOP-LOSS triggered at Z-score: {z_score:.2f}. Closing position and halting trades for this session.")
                self.portfolio.close_pair_trade(asset1, price1, asset2, price2, direction)
                self.trading_halted = True # FIX: Halt trading after a stop-loss