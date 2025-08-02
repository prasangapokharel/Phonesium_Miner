import json
import sys
import time
import requests
import multiprocessing # Keep this for client_info
from typing import Dict, Any
from .logger import Logger # Adjusted import
from .session_manager import SessionManager # Adjusted import
from .config import MinerConfig # Adjusted import

class ApiHandler:
    """Handles all interactions with the Phonesium API."""
    def __init__(self, config: MinerConfig, logger: Logger, session_manager: SessionManager):
        self.config = config
        self.logger = logger
        self.session = session_manager.session # Use the shared session

    def test_connection(self) -> bool:
        """Tests connectivity to the API endpoint with diagnostics."""
        self.logger.log('INFO', f"Testing connection to {self.config.api_url}...")
        try:
            start_time = time.time()
            response = self.session.get(self.config.api_url, timeout=10)
            response_time = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                try:
                    api_data = response.json()
                    if api_data.get('status') == 'online':
                        self.logger.log('SUCCESS', f"API endpoint online (Response: {response_time:.0f}ms)")
                        self.logger.log('SUCCESS', f"Server: {api_data.get('server', 'unknown')}")
                        self.logger.log('SUCCESS', f"API Version: {api_data.get('version', '1.0')}")
                        if 'server_load' in api_data:
                            self.logger.log('INFO', f"Server Load: {api_data['server_load']}%")
                        return True
                    else:
                        self.logger.log('ERROR', "API endpoint not responding correctly")
                        return False
                except json.JSONDecodeError:
                    self.logger.log('ERROR', "Invalid JSON response from API")
                    return False
            else:
                self.logger.log('ERROR', f"API endpoint returned status {response.status_code}")
                self.logger.log('ERROR', "Make sure your server is running on the correct port")
                return False
        except requests.exceptions.ConnectionError:
            self.logger.log('ERROR', f"Cannot connect to {self.config.api_url}")
            self.logger.log('ERROR', "Possible solutions:")
            self.logger.log('ERROR', "1. Check if web server is running")
            self.logger.log('ERROR', "2. Verify the port number")
            self.logger.log('ERROR', "3. Check firewall settings")
            self.logger.log('ERROR', "4. Verify SSL certificate if using HTTPS")
            return False
        except requests.exceptions.Timeout:
            self.logger.log('ERROR', "Connection timeout after 10s")
            return False
        except Exception as e:
            self.logger.log('ERROR', f"Connection test failed: {e}")
            return False

    def api_login(self, username: str, password: str) -> Dict[str, Any]:
        """Attempts to log in a user via the API."""
        try:
            login_data = {
                'action': 'login',
                'username': username,
                'password': password,
                'client_version': '2.0',
                'client_info': {
                    'threads': self.config.threads,
                    'cpu_count': multiprocessing.cpu_count(),
                    'platform': sys.platform
                }
            }
            response = self.session.post(
                self.config.api_url,
                data=json.dumps(login_data),
                headers={'Content-Type': 'application/json'},
                timeout=self.config.timeout
            )
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    return {'success': True, 'user_id': result.get('user_id'),
                            'username': result.get('username'), 'balance': float(result.get('balance', 0)),
                            'total_mined': float(result.get('total_mined', 0))}
                else:
                    self.logger.log('ERROR', result.get('error', 'Login failed'))
                    return {'success': False, 'error': result.get('error', 'Login failed')}
            else:
                self.logger.log('ERROR', f"Login request failed with status {response.status_code}")
                return {'success': False, 'error': f"Server error: {response.status_code}"}
        except Exception as e:
            self.logger.log('ERROR', f"API login error: {e}")
            return {'success': False, 'error': str(e)}

    def test_user_exists(self, user_id: int) -> Dict[str, Any]:
        """Checks if a user ID is still valid on the server and fetches current balance."""
        try:
            stats_data = {
                'action': 'get_stats',
                'user_id': user_id
            }
            response = self.session.post(
                self.config.api_url,
                data=json.dumps(stats_data),
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    return {'success': True, 'balance': float(result.get('balance', 0))}
            return {'success': False}
        except Exception:
            return {'success': False}

    def submit_block(self, user_id: int, block_hash: str, nonce: int, difficulty: int, hash_rate: int, system_info: Dict[str, Any]) -> Dict[str, Any]:
        """Submits a mined block to the API with retry logic."""
        payload = {
            'user_id': user_id,
            'block_hash': block_hash,
            'nonce': nonce,
            'difficulty': difficulty,
            'hash_rate': hash_rate,
            'api_secret': self.config.api_secret,
            'client_version': '2.0',
            'system_info': system_info
        }
        
        for attempt in range(self.config.retry_attempts):
            try:
                if attempt > 0:
                    self.logger.log('WARNING', f"Retry attempt {attempt + 1}/{self.config.retry_attempts}")
                    time.sleep(self.config.retry_delay * attempt)
                
                self.logger.log('INFO', f"Submitting block... (Rate: {hash_rate:.0f} H/s)")
                
                response = self.session.post(
                    self.config.api_url,
                    data=json.dumps(payload),
                    headers={'Content-Type': 'application/json'},
                    timeout=self.config.timeout
                )
                
                if response.status_code == 200:
                    try:
                        result = response.json()
                        if result.get('success'):
                            return {'success': True, 'data': result}
                        else:
                            error_msg = result.get('error', 'Unknown error')
                            self.logger.log('ERROR', f"Block rejected: {error_msg}")
                            non_retryable_errors = ['duplicate', 'already submitted', 'exists', 'invalid hash', 'expired']
                            if any(keyword in error_msg.lower() for keyword in non_retryable_errors):
                                return {'success': False, 'retryable': False, 'error': error_msg}
                            return {'success': False, 'retryable': True, 'error': error_msg}
                    except json.JSONDecodeError as e:
                        self.logger.log('ERROR', f"Invalid JSON response: {e}")
                        return {'success': False, 'retryable': True, 'error': str(e)}
                elif response.status_code == 409:
                    self.logger.log('WARNING', "Duplicate block detected")
                    return {'success': False, 'retryable': False, 'error': "Duplicate block"}
                elif response.status_code == 429:
                    self.logger.log('WARNING', "Rate limited by server, waiting 5s...")
                    time.sleep(5)
                    continue # Retry after waiting
                else:
                    self.logger.log('ERROR', f"Server error: {response.status_code}")
                    return {'success': False, 'retryable': True, 'error': f"Server error: {response.status_code}"}
            except requests.exceptions.Timeout:
                self.logger.log('ERROR', f"Request timeout (attempt {attempt + 1})")
                return {'success': False, 'retryable': True, 'error': "Request timeout"}
            except requests.exceptions.ConnectionError:
                self.logger.log('ERROR', f"Connection error (attempt {attempt + 1})")
                return {'success': False, 'retryable': True, 'error': "Connection error"}
            except Exception as e:
                self.logger.log('ERROR', f"Submission error: {e}")
                return {'success': False, 'retryable': True, 'error': str(e)}
        
        self.logger.log('ERROR', "Block submission failed after all attempts")
        return {'success': False, 'retryable': False, 'error': "Max retries exceeded"}
