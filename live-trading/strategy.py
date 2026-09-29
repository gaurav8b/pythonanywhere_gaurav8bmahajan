import pandas as pd
import logging

class DefinitiveMultiSessionStrategy:
    """
    MODIFIED: This version contains the corrected state-management logic to prevent
    the session from resetting on every bar.
    """
    def __init__(self, symbol):
        self.symbol = symbol
        self.session_states = {"AMERICA": {"bars": []}, "EUROPE": {"bars": []}, "ASIA": {"bars": []}}
        self.current_session = None
        self.setup = None
        self.entry = None
        self.opening_range = {}
        self.last_processed_day = None # To reset sessions daily

        self.SESSION_DEFINITIONS = {
            "ASIA": {"start_hour": 0, "end_hour": 7},
            "EUROPE": {"start_hour": 8, "end_hour": 15},
            "AMERICA": {"start_hour": 16, "end_hour": 23}
        }
        self.OPENING_RANGE_DURATION = pd.Timedelta(minutes=30)
        logging.info("Definitive Multi-Session Strategy (Minute Bar) initialized.")

    def _get_session(self, dt):
        """Determines the current trading session based on UTC hour."""
        for session, times in self.SESSION_DEFINITIONS.items():
            if times['start_hour'] <= dt.hour <= times['end_hour']:
                return session
        return None

    def _reset_daily_state(self):
        """Resets all session data for a new trading day."""
        logging.info(f"New calendar day. Resetting all session states.")
        self.session_states = {"AMERICA": {"bars": []}, "EUROPE": {"bars": []}, "ASIA": {"bars": []}}
        self.current_session = None
        self.setup = None
        self.entry = None
        self.opening_range = {}

    def generate_signals(self, bar, portfolio):
        bar_time_utc = bar['timestamp'].tz_convert('UTC')

        # Check if it's a new day, and if so, reset everything
        if self.last_processed_day and self.last_processed_day != bar_time_utc.date():
            self._reset_daily_state()
        self.last_processed_day = bar_time_utc.date()

        new_session = self._get_session(bar_time_utc)

        analysis_report = {
            'timestamp': bar['timestamp'].isoformat(), 'session': self.current_session, 'status': 'MONITORING',
            'opening_range_high': self.opening_range.get('high'), 'opening_range_low': self.opening_range.get('low'),
            'setup_direction': self.setup, 'entry_trigger': self.entry, 'last_bar_high': bar['high'],
            'last_bar_low': bar['low'], 'last_bar_close': bar['close'], 'condition_met': False, 'action_reason': 'N/A',
            'signal': None
        }

        # --- Corrected Session Transition Logic ---
        # Only transition if the session is new and different from the current one.
        if new_session and new_session != self.current_session:
            logging.info(f"Transitioning to {new_session} session.")
            self.current_session = new_session
            self.setup = None # Reset setup for the new session
            analysis_report.update({'status': 'TRANSITION', 'session': self.current_session, 'action_reason': f'New session started: {self.current_session}.'})

        if not self.current_session:
            analysis_report.update({'status': 'AWAITING_SESSION', 'action_reason': 'Waiting for a defined trading session to begin.'})
            return analysis_report

        # Add the current bar to the list for the active session
        # This was a bug before, as it was skipped on transition bars
        self.session_states[self.current_session]['bars'].append(bar)

        # --- Opening Range Logic ---
        if not self.setup:
            analysis_report['action_reason'] = 'Gathering bars for opening range.'
            start_hour = self.SESSION_DEFINITIONS[self.current_session]['start_hour']
            session_start_time = bar_time_utc.normalize().replace(hour=start_hour)

            # Check if enough time has passed to define the OR
            if bar_time_utc >= session_start_time + self.OPENING_RANGE_DURATION:
                # Get all bars that fall within the first 30 mins of the session
                or_bars = [b for b in self.session_states[self.current_session]['bars'] if session_start_time <= b['timestamp'].tz_convert('UTC') < session_start_time + self.OPENING_RANGE_DURATION]
                if or_bars:
                    self.opening_range['high'] = max(b['high'] for b in or_bars)
                    self.opening_range['low'] = min(b['low'] for b in or_bars)
                    last_close = or_bars[-1]['close']

                    if abs(last_close - self.opening_range['high']) < abs(last_close - self.opening_range['low']):
                        self.setup = "SHORT"
                        self.entry = self.opening_range['high']
                    else:
                        self.setup = "LONG"
                        self.entry = self.opening_range['low']

                    logging.info(f"[{self.current_session}] Opening Range defined: High={self.opening_range['high']:.2f}, Low={self.opening_range['low']:.2f}")
                    logging.info(f"[{self.current_session}] Setup: {self.setup}. Entry: {self.entry:.2f}")

                    analysis_report.update({'status': 'DEFINED', 'setup_direction': self.setup, 'entry_trigger': self.entry, 'opening_range_high': self.opening_range['high'], 'opening_range_low': self.opening_range['low'], 'action_reason': f"Opening range established. Setup: {self.setup}."})

        # --- Trade Signal Logic ---
        if self.setup and not portfolio.is_position_open():
            reason = f"Awaiting entry. Setup: {self.setup}, Trigger: {self.entry:.2f}"
            analysis_report['action_reason'] = reason
            if self.setup == "LONG" and bar['low'] <= self.entry:
                analysis_report.update({'condition_met': True, 'action_reason': f"Signal: Bar low {bar['low']:.2f} <= entry {self.entry:.2f}", 'signal': 'LONG'})
            elif self.setup == "SHORT" and bar['high'] >= self.entry:
                analysis_report.update({'condition_met': True, 'action_reason': f"Signal: Bar high {bar['high']:.2f} >= entry {self.entry:.2f}", 'signal': 'SHORT'})

        if portfolio.is_position_open():
            analysis_report.update({'status': 'IN_POSITION', 'action_reason': 'Monitoring open position.'})

        return analysis_report