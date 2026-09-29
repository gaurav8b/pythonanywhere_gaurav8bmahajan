from flask import Flask, render_template, jsonify
import threading
import logging

# Import your bot components
from data_handler import DataHandler
from bot import TradingBot
from strategy import DefinitiveMultiSessionStrategy
from portfolio import Portfolio
from logger_setup import setup_logs

app = Flask(__name__)

# =================================================================
# BOT THREAD LAUNCHER
# =================================================================

def run_trading_bot():
    """
    This function initializes and runs the bot components.
    It will be executed in a separate, single background thread.
    This prevents the race condition of multiple workers creating objects.
    """
    try:
        logging.info("Bot thread started. Initializing components...")

        # Configuration is now inside the thread
        symbol = 'BTCUSDT'
        initial_capital = 100000.0
        risk_config = {'risk_per_trade_percent': 0.015}
        trade_config = {'commission_per_trade': 1.0, 'slippage_cost_per_contract': 0.5}

        # Components are created ONCE, here in this thread
        portfolio_manager = Portfolio(
            initial_capital=initial_capital,
            risk_per_trade_percent=risk_config['risk_per_trade_percent'],
            commission_per_trade=trade_config['commission_per_trade'],
            slippage_cost_per_contract=trade_config['slippage_cost_per_contract']
        )
        data_handler = DataHandler()
        strategy = DefinitiveMultiSessionStrategy(symbol=symbol)
        bot = TradingBot(
            symbol=symbol,
            data_handler=data_handler,
            strategy=strategy,
            portfolio=portfolio_manager
        )

        # This blocks and runs the bot's main loop
        bot.run()

    except Exception as e:
        logging.critical(f"A fatal error occurred in the bot thread: {e}", exc_info=True)

# =================================================================
# FLASK WEB ROUTES
# =================================================================

@app.route('/')
def index():
    """Renders the main dashboard page."""
    return render_template('index.html')

@app.route('/data')
def data():
    """This endpoint provides data to the dashboard by reading the state file from disk."""
    try:
        # Uses the classmethod to safely read the state file created by the bot thread
        dashboard_portfolio = Portfolio.load_state_from_file()
        dashboard_data = dashboard_portfolio.get_dashboard_data()
        return jsonify(dashboard_data)
    except Exception as e:
        logging.error(f"Error in /data endpoint: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

def start_app():
    """Starts the bot thread and returns the Flask app."""
    # Setup logging first
    setup_logs()

    logging.info("Starting background bot thread...")
    thread = threading.Thread(target=run_trading_bot, daemon=True)
    thread.start()

    return app

# =================================================================
# APPLICATION ENTRY POINT
# =================================================================
# When the WSGI server (like PythonAnywhere's) imports this file, it will
# import the 'application' object.
application = start_app()

# For running locally
if __name__ == '__main__':
    application.run(host='0.0.0.0', port=5000, debug=False)