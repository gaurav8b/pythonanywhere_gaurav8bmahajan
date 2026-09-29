# app.py
import sqlite3
import pandas as pd
import plotly
import plotly.graph_objects as go
from flask import Flask, render_template
from pathlib import Path

# --- Configuration ---
# IMPORTANT: Use absolute paths for PythonAnywhere
# Replace 'your_username' with your actual PythonAnywhere username
USERNAME = "gaurav8bmahajan" # <--- CHANGE THIS
BASE_DIR = Path(f"/home/{USERNAME}/btc_ev_bot")
DB_PATH = BASE_DIR / "trades.db"

app = Flask(__name__)

def get_db_connection():
    """Establishes a connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def calculate_stats(df):
    """Calculates performance statistics from the trades dataframe."""
    if df.empty:
        return {
            'total_trades': 0, 'win_rate': 0, 'profit_factor': 0,
            'total_pnl': 0, 'avg_win': 0, 'avg_loss': 0,
            'max_drawdown': 0 # Note: Drawdown calculation is simplified here
        }

    total_trades = len(df)
    winning_trades = df[df['win'] == 1]
    losing_trades = df[df['win'] == 0]

    win_rate = (len(winning_trades) / total_trades) * 100 if total_trades > 0 else 0
    total_pnl = df['pnl_dollars'].sum()

    sum_wins = winning_trades['pnl_dollars'].sum()
    sum_losses = abs(losing_trades['pnl_dollars'].sum())
    profit_factor = sum_wins / sum_losses if sum_losses > 0 else float('inf')

    avg_win = winning_trades['pnl_dollars'].mean() if not winning_trades.empty else 0
    avg_loss = abs(losing_trades['pnl_dollars'].mean()) if not losing_trades.empty else 0

    return {
        'total_trades': total_trades,
        'win_rate': f"{win_rate:.2f}%",
        'profit_factor': f"{profit_factor:.2f}",
        'total_pnl': f"${total_pnl:,.2f}",
        'avg_win': f"${avg_win:,.2f}",
        'avg_loss': f"${avg_loss:,.2f}"
    }


@app.route('/')
def dashboard():
    """The main dashboard route."""
    conn = get_db_connection()

    # --- Fetch Data ---
    try:
        trades_df = pd.read_sql_query("SELECT * FROM trades ORDER BY exit_time DESC", conn)
        equity_df = pd.read_sql_query("SELECT * FROM equity_history ORDER BY timestamp ASC", conn)
    except pd.io.sql.DatabaseError:
        # Handle case where tables don't exist yet
        trades_df = pd.DataFrame()
        equity_df = pd.DataFrame()

    conn.close()

    # --- Generate Equity Curve Plot ---
    fig = go.Figure()
    if not equity_df.empty:
        equity_df['timestamp'] = pd.to_datetime(equity_df['timestamp'])
        fig.add_trace(go.Scatter(
            x=equity_df['timestamp'],
            y=equity_df['equity'],
            mode='lines',
            name='Equity',
            line=dict(color='#17BECF', width=2)
        ))
    fig.update_layout(
        title='Live Equity Curve',
        xaxis_title='Date',
        yaxis_title='Equity ($)',
        template='plotly_dark',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='white')
    )
    plot_json = fig.to_json()

    # --- Generate Trades Table ---
    if not trades_df.empty:
        # Format for display
        trades_df['pnl_dollars'] = trades_df['pnl_dollars'].apply(lambda x: f"${x:,.2f}")
        trades_df['entry_price'] = trades_df['entry_price'].apply(lambda x: f"${x:,.2f}")
        trades_df['exit_price'] = trades_df['exit_price'].apply(lambda x: f"${x:,.2f}")
        trades_df['size'] = trades_df['size'].apply(lambda x: f"{x:.4f}")

    trades_table_html = trades_df.to_html(
        classes='table table-dark table-striped table-hover',
        index=False,
        border=0
    )

    # --- Calculate Performance Stats ---
    # Re-fetch raw data for calculation before formatting
    conn = get_db_connection()
    raw_trades_df = pd.read_sql_query("SELECT * FROM trades", conn)
    conn.close()
    stats = calculate_stats(raw_trades_df)

    return render_template('dashboard.html', plot=plot_json, table=trades_table_html, stats=stats)

# The following is for local testing, not used by PythonAnywhere
if __name__ == '__main__':
    app.run(debug=True)
