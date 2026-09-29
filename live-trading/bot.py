import time
import logging
import pandas as pd
from logger_setup import setup_session_logger, append_to_csv, setup_logs

class TradingBot:
    def __init__(self, symbol, data_handler, strategy, portfolio, frequency='1m'):
        # This function no longer needs setup_logs() as app.py handles it.
        self.symbol = symbol
        self.data_handler = data_handler
        self.strategy = strategy
        self.portfolio = portfolio
        self.frequency = frequency
        self.is_running = True
        self.last_bar_timestamp = None
        self.session_log_file = setup_session_logger()

    def run(self):
        logging.info(f"--- Starting Trading Bot (Binance REST Polling Mode) ---")
        logging.info(f"Bot configured to trade {self.symbol} on a {self.frequency} frequency.")
        is_first_run = True

        while self.is_running:
            try:
                now_utc = pd.Timestamp.now(tz='UTC')
                next_minute = now_utc.ceil('T')
                sleep_duration = (next_minute - now_utc).total_seconds()
                time.sleep(max(0, sleep_duration))

                if is_first_run:
                    logging.info("First run: Backfilling historical data for the current session...")
                    end_dt = pd.Timestamp.now(tz='America/New_York')
                    now_utc_naive = pd.Timestamp.now()
                    session_start_utc_naive = now_utc_naive.normalize().replace(hour=16, minute=0, second=0, microsecond=0)
                    if now_utc_naive < session_start_utc_naive: session_start_utc_naive -= pd.Timedelta(days=1)
                    start_dt = session_start_utc_naive.tz_localize('UTC').tz_convert('America/New_York')

                    self.data_handler.backfill_data(self.symbol, start_dt, end_dt)
                    logging.info(f"Successfully backfilled {len(self.data_handler.get_all_bars(self.symbol))} bars.")

                    # =================================================================
                    # NEWLY ADDED: Prime the strategy with the backfilled data
                    # =================================================================
                    logging.info("Priming strategy with backfilled historical data...")
                    historical_bars = self.data_handler.get_all_bars(self.symbol)
                    for bar in historical_bars:
                        # We call this just to update the strategy's internal state
                        self.strategy.generate_signals(bar, self.portfolio)
                    logging.info("Strategy primed. Opening range should now be calculated.")
                    # =================================================================

                    is_first_run = False

                logging.info("Top of the minute. Fetching latest bar...")
                latest_bar = self.data_handler.get_latest_bar(self.symbol)

                if latest_bar and (self.last_bar_timestamp is None or latest_bar['timestamp'] > self.last_bar_timestamp):
                    self.last_bar_timestamp = latest_bar['timestamp']
                    logging.info(f"Successfully fetched new 1-minute bar for {self.symbol} at {self.last_bar_timestamp}")

                    analysis_report = self.strategy.generate_signals(latest_bar, self.portfolio)
                    append_to_csv(self.session_log_file, analysis_report)

                    signal = analysis_report.get('signal')
                    if signal and not self.portfolio.is_position_open():
                        if signal == 'LONG':
                            self.portfolio.enter_position('long', self.symbol, latest_bar['close'])
                        elif signal == 'SHORT':
                            self.portfolio.enter_position('short', self.symbol, latest_bar['close'])

                    if self.portfolio.is_position_open():
                        position = self.portfolio.state['position']
                        stop_loss_percent = 0.005

                        if position['direction'] == 'long' and latest_bar['low'] <= position['entry_price'] * (1 - stop_loss_percent):
                            self.portfolio.exit_position(position['entry_price'] * (1 - stop_loss_percent), "Stop-Loss")
                        elif position['direction'] == 'short' and latest_bar['high'] >= position['entry_price'] * (1 + stop_loss_percent):
                            self.portfolio.exit_position(position['entry_price'] * (1 + stop_loss_percent), "Stop-Loss")
                else:
                    logging.info("No new bar to process.")

            except KeyboardInterrupt:
                self.stop()
            except Exception as e:
                logging.error(f"An error occurred in the main trading loop: {e}", exc_info=True)
                time.sleep(60)

    def stop(self):
        self.is_running = False
        logging.info("Trading bot stopping...")