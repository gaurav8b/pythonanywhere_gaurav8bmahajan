# live_strategy_bot.py (Version 2.0)
import asyncio, logging, sys, requests, aiohttp, sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timezone, timedelta, time

# Import the feed manager and data tick generator
from feed import run_feed_manager, ticks

# --- 1. SETTINGS & CONFIGURATION (V2) ---
INITIAL_CAPITAL = 100_000.0
COMMISSION_BP = 2
SYMBOL = "BTCUSDT"
TIMEFRAME_MINUTES = 5
HISTORICAL_BAR_COUNT = 200 # Fetches ~16 hours of data for indicator warmup

# --- New V2 Strategy Parameters ---
ADX_THRESHOLD = 25  # Minimum ADX value to confirm a strong trend
ATR_STOP_MULTIPLIER = 2.0  # Initial stop loss multiplier (2x ATR)
ATR_TRAIL_MULTIPLIER = 1.5 # Trailing stop loss multiplier (1.5x ATR)

# --- New Trading Hours Toggle ---
# Set to True to trade 24/7 (for crypto)
# Set to False to only trade during Regular Trading Hours (for stocks, etc.)
TRADE_24_7 = True
RTH_START = time(9, 30)  # 9:30 AM (in UTC, adjust if needed)
RTH_END = time(16, 0)   # 4:00 PM (in UTC, adjust if needed)


# --- File Paths ---
USERNAME = "gaurav8bmahajan" # <--- Ensure this is your username
BOT_BASE_DIR = Path(f"/home/{USERNAME}/btc_ev_bot")
LOG_DIR = BOT_BASE_DIR / "logs"
DB_PATH = BOT_BASE_DIR / "trades.db"
log = logging.getLogger(__name__)


# --- 2. DATABASE SETUP & LOGGING (Unchanged) ---

def setup_database():
    with sqlite3.connect(DB_PATH) as conn:
        # (Code is identical to previous version)
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT, entry_time TEXT NOT NULL, exit_time TEXT NOT NULL,
            position_type TEXT NOT NULL, size REAL NOT NULL, entry_price REAL NOT NULL,
            exit_price REAL NOT NULL, pnl_dollars REAL NOT NULL, commission REAL NOT NULL,
            win INTEGER NOT NULL, exit_reason TEXT
        )""")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS equity_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, equity REAL NOT NULL
        )""")
        conn.commit()
    log.info(f"Database initialized at {DB_PATH}")

def log_trade_to_db(trade_data):
    with sqlite3.connect(DB_PATH) as conn:
        # (Code is identical to previous version)
        conn.execute("""
        INSERT INTO trades (entry_time, exit_time, position_type, size, entry_price, exit_price, pnl_dollars, commission, win, exit_reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            trade_data['entry_time'].isoformat(), trade_data['exit_time'].isoformat(),
            trade_data['type'], trade_data['size'], trade_data['entry_price'],
            trade_data['exit_price'], trade_data['pnl_dollars'], trade_data['commission'],
            int(trade_data['win']), trade_data['exit_reason']
        ))
        conn.commit()

def log_equity_to_db(timestamp, equity):
    with sqlite3.connect(DB_PATH) as conn:
        # (Code is identical to previous version)
        conn.execute("INSERT INTO equity_history (timestamp, equity) VALUES (?, ?)", (timestamp.isoformat(), equity))
        conn.commit()


# --- 3. INDICATOR CALCULATION (V2) ---

def atr(high, low, close, n=14):
    tr_df = pd.DataFrame({'high': high, 'low': low, 'close': close})
    tr_df['tr0'] = abs(tr_df['high'] - tr_df['low'])
    tr_df['tr1'] = abs(tr_df['high'] - tr_df['close'].shift(1))
    tr_df['tr2'] = abs(tr_df['low'] - tr_df['close'].shift(1))
    true_range = tr_df[['tr0', 'tr1', 'tr2']].max(axis=1)
    return true_range.ewm(alpha=1/n, adjust=False).mean()

def adx(high, low, close, n=14):
    """Calculates the Average Directional Index (ADX)."""
    df = pd.DataFrame({'High': high, 'Low': low, 'Close': close})
    df['tr'] = atr(df['High'], df['Low'], df['Close'], n)
    df['dm_plus'] = np.where((df['High'] - df['High'].shift(1)) > (df['Low'].shift(1) - df['Low']), df['High'] - df['High'].shift(1), 0)
    df['dm_minus'] = np.where((df['Low'].shift(1) - df['Low']) > (df['High'] - df['High'].shift(1)), df['Low'].shift(1) - df['Low'], 0)

    # Using EWM which is equivalent to Wilder's smoothing
    df['di_plus'] = (df['dm_plus'].ewm(alpha=1/n, adjust=False).mean() / df['tr'].ewm(alpha=1/n, adjust=False).mean()) * 100
    df['di_minus'] = (df['dm_minus'].ewm(alpha=1/n, adjust=False).mean() / df['tr'].ewm(alpha=1/n, adjust=False).mean()) * 100

    df['dx'] = (abs(df['di_plus'] - df['di_minus']) / (df['di_plus'] + df['di_minus']).replace(0, 1)) * 100
    adx_series = df['dx'].ewm(alpha=1/n, adjust=False).mean()
    return adx_series

def calculate_vwap(df):
    df['TP_Volume'] = ((df['High'] + df['Low'] + df['Close']) / 3) * df['Volume']
    grouped = df.groupby(df.index.date)
    df['Cum_TP_Volume'] = grouped['TP_Volume'].transform(pd.Series.cumsum)
    df['Cum_Volume'] = grouped['Volume'].transform(pd.Series.cumsum)
    df['vwap'] = df['Cum_TP_Volume'] / df['Cum_Volume'].replace(0, np.nan)
    df['vwap'].ffill(inplace=True)
    return df.drop(['TP_Volume', 'Cum_TP_Volume', 'Cum_Volume'], axis=1)


# --- 4. DATA FETCHING & PROCESSING (Unchanged) ---

def bootstrap_history(limit=HISTORICAL_BAR_COUNT) -> pd.DataFrame:
    # (Code is identical to previous version)
    log.info(f"Bootstrapping {limit} historical {TIMEFRAME_MINUTES}m bars from REST API...")
    url = f"https://api.binance.us/api/v3/klines?symbol={SYMBOL}&interval={TIMEFRAME_MINUTES}m&limit={limit}"
    data = requests.get(url, timeout=10).json()
    rows = []
    for kline in data:
        close_time = datetime.fromtimestamp(kline[6] / 1000, tz=timezone.utc)
        rows.append({
            "Timestamp": close_time, "Open": float(kline[1]), "High": float(kline[2]),
            "Low": float(kline[3]), "Close": float(kline[4]), "Volume": float(kline[5])
        })
    df = pd.DataFrame(rows).set_index("Timestamp")
    log.info(f"✅ Successfully bootstrapped {len(df)} bars from REST API.")
    return df

async def bars5():
    # (Code is identical to previous version)
    first = o = h = l = c = vol = None
    async for t in ticks():
        ts = datetime.fromtimestamp(t["T"] / 1000, tz=timezone.utc)
        px, size = float(t["p"]), float(t["q"])
        bucket = ts.replace(minute=(ts.minute // TIMEFRAME_MINUTES) * TIMEFRAME_MINUTES, second=0, microsecond=0)
        if first is None:
            first, o, h, l, c, vol = bucket, px, px, px, px, size
        if bucket == first:
            h, l, c, vol = max(h, px), min(l, px), px, vol + size
        else:
            yield {"Timestamp": first + timedelta(minutes=TIMEFRAME_MINUTES), "Open": o, "High": h, "Low": l, "Close": c, "Volume": vol}
            first, o, h, l, c, vol = bucket, px, px, px, px, size


# --- 5. CORE TRADING LOGIC (V2) ---

async def trade_loop(df):
    log.info("🚀 Strategy V2 loaded. Starting main trade loop...")
    equity = INITIAL_CAPITAL
    log_equity_to_db(datetime.now(timezone.utc), equity)

    # --- State Management ---
    in_position = False
    position_type = None
    position_size = 0.0
    entry_price = 0.0
    entry_time = None
    stop_loss = 0.0
    trailing_stop = 0.0 # New for V2

    async for bar in bars5():
        try:
            new_bar_df = pd.DataFrame([bar]).set_index('Timestamp')
            df = pd.concat([df, new_bar_df])
            if len(df) > 500: df = df.iloc[-500:]

            # --- V2 Indicator Calculations ---
            df['ema_50'] = df['Close'].ewm(span=50, adjust=False).mean()
            df['atr'] = atr(df['High'], df['Low'], df['Close'], 14)
            df['adx'] = adx(df['High'], df['Low'], df['Close'], 14)
            df = calculate_vwap(df)

            prev_candle = df.iloc[-2]
            curr_candle = df.iloc[-1]

            # --- Exit Logic (with Trailing Stop) ---
            if in_position:
                exit_price, reason = 0, ""

                # Update trailing stop
                if position_type == 'long':
                    new_trail = curr_candle['High'] - (curr_candle['atr'] * ATR_TRAIL_MULTIPLIER)
                    trailing_stop = max(trailing_stop, new_trail) # Stop can only move up
                    if curr_candle['Low'] <= stop_loss: exit_price, reason = stop_loss, "Stop Loss"
                    elif curr_candle['Low'] <= trailing_stop: exit_price, reason = trailing_stop, "Trailing Stop"

                elif position_type == 'short':
                    new_trail = curr_candle['Low'] + (curr_candle['atr'] * ATR_TRAIL_MULTIPLIER)
                    trailing_stop = min(trailing_stop, new_trail) # Stop can only move down
                    if curr_candle['High'] >= stop_loss: exit_price, reason = stop_loss, "Stop Loss"
                    elif curr_candle['High'] >= trailing_stop: exit_price, reason = trailing_stop, "Trailing Stop"

                if exit_price > 0:
                    pnl_points = (exit_price - entry_price) if position_type == 'long' else (entry_price - exit_price)
                    commission_cost = (position_size * entry_price + position_size * exit_price) * (COMMISSION_BP / 10000)
                    dollar_pnl = (pnl_points * position_size) - commission_cost
                    equity += dollar_pnl

                    log_trade_to_db({
                        'entry_time': entry_time, 'exit_time': curr_candle.name, 'type': position_type,
                        'size': position_size, 'entry_price': entry_price, 'exit_price': exit_price,
                        'pnl_dollars': dollar_pnl, 'commission': commission_cost, 'win': dollar_pnl > 0,
                        'exit_reason': reason
                    })
                    log_equity_to_db(curr_candle.name, equity)
                    log.info(f"✅ EXIT {position_type.upper()} @ ${exit_price:,.2f} for {reason}. PnL: ${dollar_pnl:,.2f}. New Equity: ${equity:,.2f}")
                    in_position = False # Reset state

            # --- Entry Logic ---
            is_trading_hours = TRADE_24_7 or (RTH_START <= curr_candle.name.time() < RTH_END)

            if not in_position and is_trading_hours:
                is_trending = curr_candle['adx'] > ADX_THRESHOLD

                # Long Entry: Uptrend, strong trend, and price crosses above VWAP
                if (curr_candle['Close'] > curr_candle['ema_50'] and is_trending and
                    prev_candle['Close'] < prev_candle['vwap'] and curr_candle['Close'] > curr_candle['vwap']):

                    position_type = 'long'
                    entry_price = curr_candle['Close']
                    stop_loss = entry_price - (curr_candle['atr'] * ATR_STOP_MULTIPLIER)
                    trailing_stop = stop_loss # Initialize trailing stop

                # Short Entry: Downtrend, strong trend, and price crosses below VWAP
                elif (curr_candle['Close'] < curr_candle['ema_50'] and is_trending and
                      prev_candle['Close'] > prev_candle['vwap'] and curr_candle['Close'] < curr_candle['vwap']):

                    position_type = 'short'
                    entry_price = curr_candle['Close']
                    stop_loss = entry_price + (curr_candle['atr'] * ATR_STOP_MULTIPLIER)
                    trailing_stop = stop_loss # Initialize trailing stop

                # If a trade was triggered, calculate size and execute
                if position_type:
                    in_position = True
                    entry_time = curr_candle.name
                    risk_per_share = abs(entry_price - stop_loss)
                    dollar_risk = equity * 0.01 # Risk 1% of equity per trade
                    position_size = dollar_risk / risk_per_share if risk_per_share > 0 else 0

                    if position_size > 0:
                        log.info(f"🔥 ENTRY {position_type.upper()} | Size: {position_size:.4f} | Entry: ${entry_price:,.2f} | SL: ${stop_loss:,.2f}")
                        commission_on_entry = (position_size * entry_price) * (COMMISSION_BP / 10000)
                        log_equity_to_db(curr_candle.name, equity - commission_on_entry)
                    else:
                        in_position = False # Invalidate trade if size is zero
                        position_type = None

        except Exception as e:
            log.exception(f"ERROR processing bar {bar.get('Timestamp', 'N/A')}: {e}")
            await asyncio.sleep(1)


# --- 6. BOT INITIALIZATION & MAIN EXECUTION (Unchanged) ---

async def main():
    # (Code is identical to previous version)
    BOT_BASE_DIR.mkdir(exist_ok=True)
    LOG_DIR.mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s - %(message)s', force=True,
                        handlers=[logging.FileHandler(LOG_DIR / "worker.log", mode="a"), logging.StreamHandler(sys.stdout)])

    log.info("================== BOT WORKER V2 INITIALIZING ==================")
    setup_database()
    log.info("Launching background feed manager...")
    feed_task = asyncio.create_task(run_feed_manager())
    await asyncio.sleep(5)

    try:
        df = bootstrap_history()
    except Exception as e:
        log.error(f"FATAL: Failed to bootstrap history: {e}. Exiting.")
        feed_task.cancel()
        return

    log.info("Waiting for first live bar from WebSocket to sync...")
    async for bar in bars5():
        if bar['Timestamp'] > df.index[-1]:
            log.info("✅ Live data received. Buffer is synced.")
            break
        else:
            log.info(f"Discarding stale bar: {bar['Timestamp']}")

    await trade_loop(df)
    feed_task.cancel()
    log.info("Trade loop finished.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Bot stopped by user.")
