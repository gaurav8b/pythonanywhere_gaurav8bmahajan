import logging
import os
import pandas as pd

def setup_logs():
    """
    Sets up the main application logger.
    MODIFIED: Now returns the root logger and None to match the expected
    unpacking in the main application, resolving the TypeError.
    """
    log_dir = 'logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # Configure logging to file and console
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(os.path.join(log_dir, 'live_trading.log')),
            logging.StreamHandler()
        ]
    )
    logging.info("Logger setup complete.")

    # Return the logger instance to prevent the TypeError
    return logging, None

def setup_session_logger():
    """
    Initializes the session analysis CSV log with headers if it doesn't exist.
    """
    log_dir = 'logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    log_file = os.path.join(log_dir, 'session_analysis.csv')
    headers = [
        'timestamp', 'session', 'status', 'opening_range_high', 'opening_range_low',
        'setup_direction', 'entry_trigger', 'last_bar_high', 'last_bar_low',
        'last_bar_close', 'condition_met', 'action_reason'
    ]

    if not os.path.exists(log_file):
        pd.DataFrame(columns=headers).to_csv(log_file, index=False)
    return log_file

def append_to_csv(file_path, data_dict):
    """Appends a dictionary of data as a new row to a CSV file."""
    try:
        # Ensure all headers are present, filling missing with None
        headers = pd.read_csv(file_path, nrows=0).columns.tolist()
        data_to_append = {h: data_dict.get(h) for h in headers}

        df = pd.DataFrame([data_to_append])
        df.to_csv(file_path, mode='a', header=False, index=False)
    except Exception as e:
        logging.error(f"Failed to append to CSV {file_path}: {e}")