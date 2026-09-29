import requests
import pandas as pd
from datetime import datetime, timedelta
from logger_setup import setup_logs

event_logger, _ = setup_logs()

class StatArbDataHandler:
    def __init__(self):
        self.base_url = "https://api.binance.us/api/v3"
        event_logger.info("StatArbDataHandler initialized for Binance.US API.")

    def fetch_pair_data(self, asset1_symbol, asset2_symbol, hours):
        """Fetches and merges historical data for two assets."""
        end_dt = datetime.utcnow()
        start_dt = end_dt - timedelta(hours=hours)

        event_logger.info(f"Fetching historical data for {asset1_symbol} and {asset2_symbol} for the last {hours} hours.")

        df1 = self._fetch_asset_data(asset1_symbol, start_dt, end_dt)
        if df1 is None: return None

        df2 = self._fetch_asset_data(asset2_symbol, start_dt, end_dt)
        if df2 is None: return None

        # Merge the close prices of the two assets into a single DataFrame
        pair_df = pd.DataFrame(index=df1.index)
        pair_df[asset1_symbol] = df1['close']
        pair_df[asset2_symbol] = df2['close']

        return pair_df.dropna()

    def _fetch_asset_data(self, symbol, start_dt, end_dt):
        """Fetches historical 1-minute bars for a single asset."""
        params = {
            'symbol': symbol,
            'interval': '1m',
            'startTime': int(start_dt.timestamp() * 1000),
            'endTime': int(end_dt.timestamp() * 1000),
            'limit': 1000
        }
        all_data = []

        # Loop to handle fetching more than 1000 bars if needed
        while True:
            try:
                url = f"{self.base_url}/klines"
                response = requests.get(url, params=params)
                response.raise_for_status()
                data = response.json()

                if not data: break

                all_data.extend(data)
                params['startTime'] = data[-1][0] + 1
            except requests.exceptions.RequestException as e:
                event_logger.error(f"Error fetching historical data for {symbol}: {e}")
                return None

        if not all_data: return None

        df = pd.DataFrame(all_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        numeric_cols = ['open', 'high', 'low', 'close', 'volume']
        df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors='coerce')

        return df[['close']]