import time
from datetime import datetime
from logger_setup import setup_logs
from stat_arb_portfolio import StatArbPortfolio
from stat_arb_strategy import StatisticalArbitrageStrategy
from stat_arb_data_handler import StatArbDataHandler

def run_stat_arb_bot():
    """Initializes and runs the statistical arbitrage trading bot."""
    event_logger, _ = setup_logs()
    event_logger.info("--- Starting Statistical Arbitrage Bot ---")

    portfolio_manager = StatArbPortfolio.load_state()
    data_handler = StatArbDataHandler()
    strategy = StatisticalArbitrageStrategy(portfolio_manager, data_handler)

    # Main execution loop
    last_assessment_hour = -1
    while True:
        try:
            current_hour = datetime.now().hour

            # Re-assess the cointegration relationship once every hour
            if current_hour != last_assessment_hour:
                strategy.assess_and_update()
                last_assessment_hour = current_hour

            # Check for trading signals every minute
            strategy.on_bar()

            # Wait for 60 seconds before the next check
            time.sleep(60)

        except KeyboardInterrupt:
            event_logger.info("--- Shutting down Statistical Arbitrage Bot ---")
            break
        except Exception as e:
            event_logger.error(f"An unexpected error occurred in the stat arb main loop: {e}", exc_info=True)
            time.sleep(10)

if __name__ == '__main__':
    run_stat_arb_bot()