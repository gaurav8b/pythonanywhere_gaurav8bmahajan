# worker.py
import asyncio
import logging
import sys
from pathlib import Path

# IMPORTANT: Add the project directory to the path so it can find other modules
# Replace 'your_username' with your actual PythonAnywhere username
USERNAME = "gaurav8bmahajan" # <--- CHANGE THIS
project_path = f'/home/{USERNAME}/btc_ev_bot'
if project_path not in sys.path:
    sys.path.insert(0, project_path)

# Now that the path is set, we can import the bot's main function
from live_strategy_bot import main

# Set up logging for the worker process
log_dir = Path(project_path) / "logs"
log_dir.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s [WORKER] - %(message)s',
    force=True,
    handlers=[
        logging.FileHandler(log_dir / "worker.log", mode="a"),
        logging.StreamHandler(sys.stdout)
    ]
)

if __name__ == "__main__":
    logging.info("Starting trading bot worker...")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Worker stopped manually.")
    except Exception as e:
        logging.exception(f"Worker crashed with an unexpected error: {e}")
    finally:
        logging.info("Worker has shut down.")
