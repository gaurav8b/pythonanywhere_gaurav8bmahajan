import logging
import pandas as pd
from binance.client import Client

class DataHandler:
    def __init__(self, api_key=None, api_secret=None):
        self.client = Client(api_key, api_secret, tld='us')
        self.bars = {}
        logging.info("Data Handler initialized for Binance.US API.")

    def get_latest_bar(self, symbol):
        try:
            klines = self.client.get_klines(symbol=symbol, interval=Client.KLINE_INTERVAL_1MINUTE, limit=2)
            if not klines: return None

            latest_closed_kline = klines[-2]
            bar = self._format_kline(latest_closed_kline)

            if symbol not in self.bars: self.bars[symbol] = []

            if not self.bars[symbol] or self.bars[symbol][-1]['timestamp'] < bar['timestamp']:
                self.bars[symbol].append(bar)
                return bar
            return None
        except Exception as e:
            logging.error(f"Error fetching latest bar for {symbol}: {e}")
            return None

    def backfill_data(self, symbol, start_dt, end_dt):
        try:
            logging.info(f"Fetching historical data for {symbol} from {start_dt} to {end_dt}...")
            start_str = start_dt.strftime("%d %b %Y %H:%M:%S")
            end_str = end_dt.strftime("%d %b %Y %H:%M:%S")
            klines = self.client.get_historical_klines(symbol, Client.KLINE_INTERVAL_1MINUTE, start_str, end_str)

            if symbol not in self.bars: self.bars[symbol] = []

            # Clear previous bars before backfilling to prevent duplicates
            self.bars[symbol].clear()

            for k in klines:
                bar = self._format_kline(k)
                self.bars[symbol].append(bar)

            self.bars[symbol].sort(key=lambda b: b['timestamp'])
        except Exception as e:
            logging.error(f"Error during data backfill for {symbol}: {e}")

    # =================================================================
    # NEWLY ADDED HELPER METHOD
    # =================================================================
    def get_all_bars(self, symbol):
        """Returns all currently held bars for a symbol."""
        return self.bars.get(symbol, [])
    # =================================================================

    def _format_kline(self, kline):
        ts = pd.to_datetime(kline[0], unit='ms', utc=True)
        ts_ny = ts.tz_convert('America/New_York')
        return {'timestamp': ts_ny, 'open': float(kline[1]), 'high': float(kline[2]), 'low': float(kline[3]), 'close': float(kline[4]), 'volume': float(kline[5])}