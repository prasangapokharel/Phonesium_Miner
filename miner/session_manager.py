import os
import time
import pickle
import requests
from typing import Dict, Any
from .logger import Logger # Adjusted import
from .config import MinerConfig # Adjusted import

class SessionManager:
    """Manages HTTP sessions and user session caching."""
    def __init__(self, config: MinerConfig, logger: Logger):
        self.config = config
        self.logger = logger
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Phonesium-Miner/2.0',
            'Accept': 'application/json',
            'Connection': 'keep-alive',
            'Accept-Encoding': 'gzip, deflate'
        })
        
        # Connection pooling with retry strategy
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=20,
            pool_maxsize=50,
            max_retries=requests.adapters.Retry(
                total=3,
                backoff_factor=0.3,
                status_forcelist=[500, 502, 503, 504]
            )
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

    def save_session_cache(self, user_id: int, username: str, stats: Dict[str, Any]):
        """Saves user session data and relevant stats to a cache file."""
        try:
            cache_data = {
                'user_id': user_id,
                'username': username,
                'timestamp': time.time(),
                'stats': stats.copy()
            }
            with open(self.config.cache_file, 'wb') as f:
                pickle.dump(cache_data, f)
            self.logger.log('INFO', f"Session cached for user: {username}")
        except Exception as e:
            self.logger.log('WARNING', f"Failed to save session cache: {e}")

    def load_session_cache(self) -> Dict[str, Any]:
        """Loads user session data from the cache file if valid."""
        try:
            if os.path.exists(self.config.cache_file):
                with open(self.config.cache_file, 'rb') as f:
                    cache_data = pickle.load(f)
                
                # Check if cache is not too old (24 hours)
                if time.time() - cache_data.get('timestamp', 0) < 86400:
                    self.logger.log('SUCCESS', f"Loaded cached session: {cache_data.get('username')} (ID: {cache_data.get('user_id')})")
                    return cache_data
                else:
                    self.logger.log('INFO', "Session cache expired")
                    os.remove(self.config.cache_file)
        except Exception as e:
            self.logger.log('WARNING', f"Failed to load session cache: {e}")
            if os.path.exists(self.config.cache_file):
                try:
                    os.remove(self.config.cache_file)
                except:
                    pass
        return {}

    def clear_session_cache(self):
        """Clears the session cache file."""
        try:
            if os.path.exists(self.config.cache_file):
                os.remove(self.config.cache_file)
                self.logger.log('INFO', "Session cache cleared")
        except Exception as e:
            self.logger.log('WARNING', f"Failed to clear session cache: {e}")
