import os
from datetime import datetime
from typing import Optional

class Logger:
    """Handles all logging operations with color coding and optional file output."""
    def __init__(self):
        self.colors = {
            'SUCCESS': '\033[92m',  # Green
            'ERROR': '\033[91m',    # Red
            'WARNING': '\033[93m',  # Yellow
            'INFO': '\033[94m',     # Blue
            'DEBUG': '\033[95m',    # Magenta
            'RESET': '\033[0m'      # Reset
        }
        self.log_to_file_enabled = os.getenv('LOG_TO_FILE', 'false').lower() == 'true'

    def log(self, level: str, message: str, thread_id: Optional[int] = None):
        """Prints a log message to console with color coding and timestamp."""
        timestamp = datetime.now().strftime('%H:%M:%S')
        thread_prefix = f"cpu{thread_id}" if thread_id is not None else "sys0"
        
        color = self.colors.get(level, self.colors['RESET'])
        log_message = f"{color}{timestamp}  {thread_prefix}  {message}{self.colors['RESET']}"
        print(log_message)
        
        if self.log_to_file_enabled:
            self._write_to_log_file(f"{timestamp}  {thread_prefix}  {message}")

    def _write_to_log_file(self, message: str):
        """Writes a log message to a daily log file."""
        try:
            log_dir = 'logs'
            if not os.path.exists(log_dir):
                os.makedirs(log_dir)
            
            log_file = os.path.join(log_dir, f"phonesium_miner_{datetime.now().strftime('%Y%m%d')}.log")
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"{message}\n")
        except Exception:
            pass # Suppress errors to avoid spamming console if log file fails
