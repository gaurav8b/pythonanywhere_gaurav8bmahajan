# live_strategy_bot.py
import asyncio, logging, sys, requests, aiohttp
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Import the feed manager and data tick generator
from feed import run_feed_manager, ticks

# --- 1. SETTINGS & CONFIGURATION ---
INITIAL_CAPITAL = 100_000.0
KELLY_FRACTION = 0.5  # Use 50% of the Kelly-suggested fraction
COMMISSION_BP = 2 # Commission in basis points (2bp = 0.02%)
SYMBOL = "BTCUSDT"
TIMEFRAME_MINUTES = 5
HISTORICAL_BAR_COUNT = 200 # Number of bars to fetch for indicator warm-up

# --- File Paths ---
BOT_BASE_DIR = Path.home() / "btc_strategy_bot"
LOG_DIR = BOT_BASE_DIR / "logs"
log = logging.getLogger(__name__)


# --- 2. INDICATOR & PERFORMANCE CALCULATION FUNCTIONS (from backtest) ---

def atr(high, low, close, n=14):
    tr_df = pd.DataFrame({'high': high, 'low': low, 'close': close})
    tr_df['tr0'] = abs(tr_df['high'] - tr_df['low'])
    tr_df['tr1'] = abs(tr_df['high'] - tr_df['close'].shift(1))
    tr_df['tr2'] = abs(tr_df['low'] - tr_df['close'].shift(1))
    true_range = tr_df[['tr0', 'tr1', 'tr2']].max(axis=1)
    return true_range.ewm(alpha=1/n, adjust=False).mean()

def rsi(close, n=14):
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/n, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/n, adjust=False).mean()
    # Avoid division by zero
    if loss.iloc[-1] == 0: return 100.0
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_vwap(df):
    # The 'day' is determined by the UTC date
    df['TP_Volume'] = ((df['High'] + df['Low'] + df['Close']) / 3) * df['Volume']
    grouped = df.groupby(df.index.date)
    df['Cum_TP_Volume'] = grouped['TP_Volume'].transform(pd.Series.cumsum)
    df['Cum_Volume'] = grouped['Volume'].transform(pd.Series.cumsum)
    df['vwap'] = df['Cum_TP_Volume'] / df['Cum_Volume'].replace(0, np.nan)
    # Forward fill to handle periods with no volume at the start of a new day
    df['vwap'].ffill(inplace=True)
    return df.drop(['TP_Volume', 'Cum_TP_Volume', 'Cum_Volume'], axis=1)


def print_performance_report(trade_history, equity_curve, period_name="Live Performance"):
    """Prints a detailed summary of trading performance."""
    if not trade_history:
        log.info(f"\n--- No trades executed yet. ---")
        return

    results_df = pd.DataFrame(trade_history)
    total_trades = len(results_df)
    returns_s = results_df['pnl_dollars']

    log.info(f"\n--- Performance Report: {period_name} ---")
    log.info(f"Ending Equity: ${equity_curve[-1]:,.2f}")
    log.info(f"Total Net Profit/Loss: ${returns_s.sum():,.2f}")
    log.info("-" * 40)

    # In a live setting, drawdown is calculated on the equity curve
    equity_s = pd.Series(equity_curve)
    peak = equity_s.expanding(min_periods=1).max()
    drawdown = (equity_s - peak) / peak
    max_drawdown = drawdown.min() * 100
    log.info(f"Max Drawdown: {max_drawdown:.2f}%")

    # Per-trade risk metrics
    sharpe_ratio = sortino_ratio = 0
    if returns_s.std() != 0:
        sharpe_ratio = returns_s.mean() / returns_s.std()
        downside_returns = returns_s[returns_s < 0]
        if len(downside_returns) > 1 and downside_returns.std() > 0:
            sortino_ratio = returns_s.mean() / downside_returns.std()
    log.info(f"Sharpe Ratio (per-trade): {sharpe_ratio:.2f}")
    log.info(f"Sortino Ratio (per-trade): {sortino_ratio:.2f}")

    winning_trades = results_df[results_df['win']]
    losing_trades = results_df[~results_df['win']]
    profit_factor = np.inf
    if abs(losing_trades['pnl_dollars'].sum()) > 0:
        profit_factor = winning_trades['pnl_dollars'].sum() / abs(losing_trades['pnl_dollars'].sum())
    log.info(f"Profit Factor: {profit_factor:.2f}")
    log.info("-" * 40)

    win_rate = (len(winning_trades) / total_trades) * 100 if total_trades > 0 else 0
    avg_win = winning_trades['pnl_dollars'].mean() if not winning_trades.empty else 0
    avg_loss = abs(losing_trades['pnl_dollars'].mean()) if not losing_trades.empty else 0
    log.info(f"Total Trades: {total_trades}")
    log.info(f"Win Rate: {win_rate:.2f}%")
    log.info(f"Average Win: ${avg_win:,.2f}  |  Average Loss: ${avg_loss:,.2f}")

    if not results_df.empty:
        streaks = (results_df['win'] != results_df['win'].shift()).cumsum()
        win_streak = results_df.groupby(streaks)['win'].sum().max()
        loss_streak = (streaks.value_counts() - results_df.groupby(streaks)['win'].sum()).max()
        avg_duration_seconds = results_df['duration'].dt.total_seconds().mean()
        log.info(f"Longest Win Streak: {int(win_streak)}  |  Longest Loss Streak: {int(loss_streak)}")
        log.info(f"Average Trade Duration: {timedelta(seconds=avg_duration_seconds)}")

    log.info("-" * 40)


# --- 3. DATA FETCHING & PROCESSING ---

def bootstrap_history(limit=HISTORICAL_BAR_COUNT) -> pd.DataFrame:
    """Fetches historical k-line data from Binance REST API to warm up indicators."""
    log.info(f"Bootstrapping {limit} historical {TIMEFRAME_MINUTES}m bars from REST API...")
    url = f"https://api.binance.us/api/v3/klines?symbol={SYMBOL}&interval={TIMEFRAME_MINUTES}m&limit={limit}"
    data = requests.get(url, timeout=10).json()
    rows = []
    for kline in data:
        # Use the k-line 'close time' for the timestamp
        close_time = datetime.fromtimestamp(kline[6] / 1000, tz=timezone.utc)
        rows.append({
            "Timestamp": close_time, "Open": float(kline[1]), "High": float(kline[2]),
            "Low": float(kline[3]), "Close": float(kline[4]), "Volume": float(kline[5])
        })
    df = pd.DataFrame(rows).set_index("Timestamp")
    log.info(f"✅ Successfully bootstrapped {len(df)} bars from REST API.")
    return df

async def bars5():
    """Asynchronously aggregates ticks into 5-minute OHLCV bars."""
    first = o = h = l = c = vol = None
    async for t in ticks():
        ts = datetime.fromtimestamp(t["T"] / 1000, tz=timezone.utc)
        px, size = float(t["p"]), float(t["q"])

        # Create a bucket for the current 5-minute interval
        bucket = ts.replace(minute=(ts.minute // TIMEFRAME_MINUTES) * TIMEFRAME_MINUTES, second=0, microsecond=0)

        if first is None:
            first, o, h, l, c, vol = bucket, px, px, px, px, size

        if bucket == first:
            h, l, c, vol = max(h, px), min(l, px), px, vol + size
        else:
            # The bar is complete, yield it. The timestamp is the bar's closing time.
            yield {"Timestamp": first + timedelta(minutes=TIMEFRAME_MINUTES), "Open": o, "High": h, "Low": l, "Close": c, "Volume": vol}
            first, o, h, l, c, vol = bucket, px, px, px, px, size


# --- 4. CORE TRADING LOGIC ---

async def trade_loop(df):
    """The main loop where trading decisions are made based on the strategy."""
    log.info("🚀 Strategy loaded. Starting main trade loop for BTCUSDT...")

    # --- Strategy State ---
    equity = INITIAL_CAPITAL
    equity_curve = [INITIAL_CAPITAL]
    trade_history = []
    in_position = False
    position_type = None # 'long' or 'short'
    position_size = 0.0
    entry_price = 0.0
    entry_time = None
    stop_loss = 0.0

    last_report_date = datetime.now(timezone.utc).date()

    # --- Main Loop ---
    async for bar in bars5():
        # --- A. Update Data & Indicators ---
        new_bar_df = pd.DataFrame([bar]).set_index('Timestamp')
        df = pd.concat([df, new_bar_df])
        if len(df) > 500: df = df.iloc[-500:] # Memory management

        # Calculate all indicators
        df['ema_9'] = df['Close'].ewm(span=9, adjust=False).mean()
        df['ema_21'] = df['Close'].ewm(span=21, adjust=False).mean()
        df['ema_50'] = df['Close'].ewm(span=50, adjust=False).mean()
        df['atr'] = atr(df['High'], df['Low'], df['Close'], 14)
        df['rsi'] = rsi(df['Close'], 14)
        df = calculate_vwap(df)

        # Calculate daily data for trend condition
        daily_data = df.groupby(df.index.date).agg(
            High=('High', 'max'), Low=('Low', 'min'), Atr=('atr', 'mean')
        )
        df['prev_day_high'] = daily_data['High'].shift(1).reindex(df.index.date).values
        df['prev_day_low'] = daily_data['Low'].shift(1).reindex(df.index.date).values

        # Trend day condition
        historical_avg_atr = daily_data['Atr'].rolling(window=20).mean().shift(1)
        yesterdays_atr = daily_data['Atr'].shift(1)
        is_trend_map = (yesterdays_atr > historical_avg_atr * 1.2)
        df['is_trend_day'] = df.index.date.map(is_trend_map.to_dict()).fillna(False)

        # Get latest data
        prev_candle = df.iloc[-2]
        curr_candle = df.iloc[-1]

        # --- B. Check for Periodic Reporting ---
        current_date = curr_candle.name.date()
        if current_date > last_report_date:
            print_performance_report(trade_history, equity_curve, f"Report for {last_report_date.isoformat()}")
            last_report_date = current_date


        # --- C. Position Management (Exit Logic) ---
        if in_position:
            exit_price, reason = 0, ""

            # Stop Loss
            if position_type == 'long' and curr_candle['Low'] <= stop_loss:
                exit_price, reason = stop_loss, "Stop Loss"
            elif position_type == 'short' and curr_candle['High'] >= stop_loss:
                exit_price, reason = stop_loss, "Stop Loss"
            # Trend Bend Exit
            elif position_type == 'long' and prev_candle['Close'] < prev_candle['ema_21']:
                exit_price, reason = curr_candle['Open'], "Trend Bend Exit"
            elif position_type == 'short' and prev_candle['Close'] > prev_candle['ema_21']:
                exit_price, reason = curr_candle['Open'], "Trend Bend Exit"

            if exit_price > 0:
                pnl_points = (exit_price - entry_price) if position_type == 'long' else (entry_price - exit_price)
                commission_cost = (position_size * entry_price + position_size * exit_price) * (COMMISSION_BP / 10000)
                dollar_pnl = (pnl_points * position_size) - commission_cost

                equity += dollar_pnl
                equity_curve.append(equity)

                trade_history.append({
                    'pnl_dollars': dollar_pnl, 'win': dollar_pnl > 0,
                    'type': position_type, 'duration': curr_candle.name - entry_time
                })

                log.info(f"✅ EXIT {position_type.upper()} @ ${exit_price:,.2f}. Reason: {reason}. PnL: ${dollar_pnl:,.2f}. New Equity: ${equity:,.2f}")

                # Reset position state
                in_position = False
                position_type, position_size, entry_price, entry_time, stop_loss = None, 0, 0, None, 0

        # --- D. Entry Logic ---
        if not in_position and prev_candle['is_trend_day'] and pd.notna(prev_candle['prev_day_low']):
            atr_val = prev_candle['atr']
            risk_per_trade = 0.01 # Default risk percentage

            # Kelly Criterion Adjustment (optional, based on recent performance)
            if len(trade_history) >= 30:
                past_trades = pd.DataFrame(trade_history[-30:])
                W = past_trades['win'].mean()
                win_pnl = past_trades[past_trades['win']]['pnl_dollars'].mean()
                loss_pnl = abs(past_trades[~past_trades['win']]['pnl_dollars'].mean())
                if loss_pnl > 0:
                    R = win_pnl / loss_pnl
                    kelly_pct = W - ((1 - W) / R)
                    if kelly_pct > 0:
                        risk_per_trade = min(kelly_pct * KELLY_FRACTION, 0.025) # Cap risk at 2.5%

            should_trade = False
            long_conf_dist = abs(prev_candle['vwap'] - prev_candle['prev_day_low'])
            short_conf_dist = abs(prev_candle['vwap'] - prev_candle['prev_day_high'])
            confidence_score = 1.0

            # Long Entry Condition
            if prev_candle['Close'] > prev_candle['ema_50'] and prev_candle['Low'] <= prev_candle['vwap'] and prev_candle['Close'] > prev_candle['ema_9'] and prev_candle['rsi'] > 55 and long_conf_dist < (2 * atr_val):
                entry_price, stop_loss = curr_candle['Open'], curr_candle['Open'] - (2 * atr_val)
                position_type, should_trade = 'long', True
                if long_conf_dist < (0.5 * atr_val): confidence_score = 1.2

            # Short Entry Condition
            elif prev_candle['Close'] < prev_candle['ema_50'] and prev_candle['High'] >= prev_candle['vwap'] and prev_candle['Close'] < prev_candle['ema_9'] and prev_candle['rsi'] < 45 and short_conf_dist < (2 * atr_val):
                entry_price, stop_loss = curr_candle['Open'], curr_candle['Open'] + (2 * atr_val)
                position_type, should_trade = 'short', True
                if short_conf_dist < (0.5 * atr_val): confidence_score = 1.2

            if should_trade:
                risk_per_share = abs(entry_price - stop_loss)
                if risk_per_share > 0:
                    final_risk = risk_per_trade * confidence_score
                    dollar_risk = equity * final_risk
                    calculated_size = dollar_risk / risk_per_share

                    if calculated_size > 0:
                        in_position = True
                        position_size = calculated_size
                        entry_time = curr_candle.name
                        log.info(f"🔥 ENTRY {position_type.upper()} | Size: {position_size:.4f} | Entry: ${entry_price:,.2f} | SL: ${stop_loss:,.2f} | Risk %: {final_risk:.2%}")

    # Return final results for end-of-session report
    return trade_history, equity_curve


# --- 5. BOT INITIALIZATION & MAIN EXECUTION ---

async def main():
    log.info("Launching background feed manager...")
    feed_task = asyncio.create_task(run_feed_manager())
    await asyncio.sleep(5) # Give it time to connect

    try:
        df = bootstrap_history()
    except (requests.RequestException, aiohttp.ClientError) as e:
        log.error(f"FATAL: Failed to bootstrap history via REST: {e}. Cannot start. Exiting.")
        feed_task.cancel()
        return

    # Wait until the DataFrame is synced with live data
    log.info("Waiting for first live bar from WebSocket to sync...")
    async for bar in bars5():
        if bar['Timestamp'] > df.index[-1]:
            log.info("✅ Live data received. Buffer is synced.")
            break
        else:
            log.info(f"Discarding stale bar: {bar['Timestamp']}")

    # Run the main trading loop and get the results upon exit
    trade_history, equity_curve = await trade_loop(df)

    log.info("Trade loop has finished.")
    feed_task.cancel()
    return trade_history, equity_curve


if __name__ == "__main__":
    BOT_BASE_DIR.mkdir(exist_ok=True)
    LOG_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s - %(message)s',
        force=True,
        handlers=[
            logging.FileHandler(LOG_DIR / "live_bot.log", mode="a"),
            logging.StreamHandler(sys.stdout)
        ]
    )
    log.info("================== LIVE STRATEGY BOT INITIALIZING ==================")
    final_trades = []
    final_equity = [INITIAL_CAPITAL]
    try:
        final_trades, final_equity = asyncio.run(main())
    except KeyboardInterrupt:
        log.warning("Bot stopped by user (Ctrl+C).")
    except Exception as e:
        log.exception(f"An unexpected error occurred: {e}")
    finally:
        log.info("\nBot shutting down. Generating final performance report...")
        print_performance_report(final_trades, final_equity, "Final Lifetime Performance")
        log.info("================== BOT SHUTDOWN COMPLETE ==================")