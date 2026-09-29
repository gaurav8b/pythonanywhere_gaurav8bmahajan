import logging
import pandas as pd
import os

def setup_logging():
    """Sets up the basic INFO level logger."""
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def setup_session_logger():
    """
    Initializes the session analysis CSV log with headers if it doesn't exist.
    Creates the 'logs' directory if it's missing.
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
        df = pd.DataFrame([data_dict])
        df.to_csv(file_path, mode='a', header=False, index=False)
    except Exception as e:
        logging.error(f"Failed to append to CSV {file_path}: {e}")