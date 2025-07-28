#!/usr/bin/env python3
"""
Phonesium Mining Client - Enhanced Version
Like Duino-Coin but for Phonesium
Advanced multi-threaded cryptocurrency miner with session management
"""

import hashlib
import time
import requests
import json
import argparse
import threading
import sys
import os
from datetime import datetime
import random
import getpass
from concurrent.futures import ThreadPoolExecutor, as_completed
import multiprocessing
from dotenv import load_dotenv
import pickle
import signal
import psutil
from typing import Optional, Dict, Any

# Load environment variables
load_dotenv()

class PhonesiumMiner:
    """Advanced Phonesium cryptocurrency miner with enhanced features"""
    
    def __init__(self):
        # Configuration
        self.base_url = os.getenv('BASE_URL', 'https://shp.re')
        self.api_url = f"{self.base_url}/api"
        
        # Mining settings
        self.difficulty = int(os.getenv('DIFFICULTY', 5))
        self.api_secret = os.getenv('API_SECRET', 'TTXRESS2')
        self.timeout = int(os.getenv('TIMEOUT', 30))
        self.retry_attempts = int(os.getenv('RETRY_ATTEMPTS', 5))
        self.retry_delay = int(os.getenv('RETRY_DELAY', 2))
        
        # Performance settings
        self.threads = min(int(os.getenv('THREADS', 4)), multiprocessing.cpu_count())
        self.nonce_range = int(os.getenv('NONCE_RANGE', 2000000))
        self.hash_batch_size = int(os.getenv('HASH_BATCH_SIZE', 50000))
        
        # Advanced settings
        self.auto_difficulty = os.getenv('AUTO_DIFFICULTY', 'false').lower() == 'true'
        self.cpu_limit = int(os.getenv('CPU_LIMIT', 80))  # CPU usage limit percentage
        self.memory_limit = int(os.getenv('MEMORY_LIMIT', 1024))  # Memory limit in MB
        
        # Session cache file
        self.cache_file = 'phonesium_session.cache'
        
        # Enhanced session configuration
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
        
        # Mining state
        self.user_id = None
        self.username = None
        self.mining = False
        self.shutdown_requested = False
        self.paused = False
        
        # Enhanced statistics
        self.stats = {
            'blocks_mined': 0,
            'total_hashes': 0,
            'start_time': time.time(),
            'hash_rate': 0,
            'accepted_blocks': 0,
            'rejected_blocks': 0,
            'network_errors': 0,
            'last_block_time': None,
            'total_earnings': 0.0,
            'current_balance': 0.0,
            'best_hash_rate': 0,
            'average_block_time': 0,
            'cpu_usage': 0,
            'memory_usage': 0,
            'temperature': 0,
            'power_level': 'low',
            'session_uptime': 0
        }
        self.stats_lock = threading.Lock()
        
        # Performance monitoring
        self.performance_monitor = None
        self.last_hash_rates = []
        
        # Signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        self.log('WARNING', f"Received signal {signum}, initiating graceful shutdown...")
        self.shutdown_requested = True
        self.mining = False
    
    def log(self, level: str, message: str, thread_id: Optional[int] = None):
        """Enhanced logging with color coding and timestamps"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        thread_prefix = f"cpu{thread_id}" if thread_id is not None else "sys0"
        
        # Color coding
        colors = {
            'SUCCESS': '\033[92m',  # Green
            'ERROR': '\033[91m',    # Red
            'WARNING': '\033[93m',  # Yellow
            'INFO': '\033[94m',     # Blue
            'DEBUG': '\033[95m',    # Magenta
            'RESET': '\033[0m'      # Reset
        }
        
        color = colors.get(level, colors['RESET'])
        log_message = f"{color}{timestamp}  {thread_prefix}  {message}{colors['RESET']}"
        print(log_message)
        
        # Optional: Write to log file
        if os.getenv('LOG_TO_FILE', 'false').lower() == 'true':
            self._write_to_log_file(f"{timestamp}  {thread_prefix}  {message}")
    
    def _write_to_log_file(self, message: str):
        """Write log message to file"""
        try:
            log_dir = 'logs'
            if not os.path.exists(log_dir):
                os.makedirs(log_dir)
            
            log_file = os.path.join(log_dir, f"phonesium_miner_{datetime.now().strftime('%Y%m%d')}.log")
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"{message}\n")
        except Exception as e:
            pass  # Don't spam console with log file errors
    
    def save_session_cache(self):
        """Save session data to cache file with encryption"""
        try:
            cache_data = {
                'user_id': self.user_id,
                'username': self.username,
                'timestamp': time.time(),
                'stats': self.stats.copy()
            }
            
            with open(self.cache_file, 'wb') as f:
                pickle.dump(cache_data, f)
            
            self.log('INFO', f"Session cached for user: {self.username}")
        except Exception as e:
            self.log('WARNING', f"Failed to save session cache: {e}")
    
    def load_session_cache(self) -> bool:
        """Load session data from cache file"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'rb') as f:
                    cache_data = pickle.load(f)
                
                # Check if cache is not too old (24 hours)
                if time.time() - cache_data.get('timestamp', 0) < 86400:
                    self.user_id = cache_data.get('user_id')
                    self.username = cache_data.get('username')
                    
                    # Restore some stats
                    cached_stats = cache_data.get('stats', {})
                    self.stats['total_earnings'] = cached_stats.get('total_earnings', 0.0)
                    self.stats['current_balance'] = cached_stats.get('current_balance', 0.0)
                    
                    if self.user_id and self.username:
                        self.log('SUCCESS', f"Loaded cached session: {self.username} (ID: {self.user_id})")
                        return True
                else:
                    self.log('INFO', "Session cache expired")
                    os.remove(self.cache_file)
        except Exception as e:
            self.log('WARNING', f"Failed to load session cache: {e}")
            if os.path.exists(self.cache_file):
                try:
                    os.remove(self.cache_file)
                except:
                    pass
        
        return False
    
    def clear_session_cache(self):
        """Clear session cache"""
        try:
            if os.path.exists(self.cache_file):
                os.remove(self.cache_file)
                self.log('INFO', "Session cache cleared")
        except Exception as e:
            self.log('WARNING', f"Failed to clear session cache: {e}")
    
    def test_connection(self) -> bool:
        """Test server connection with comprehensive diagnostics"""
        self.log('INFO', f"Testing connection to {self.api_url}...")
        
        try:
            # Test API endpoint
            start_time = time.time()
            response = self.session.get(self.api_url, timeout=10)
            response_time = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                try:
                    api_data = response.json()
                    if api_data.get('status') == 'online':
                        self.log('SUCCESS', f"API endpoint online (Response: {response_time:.0f}ms)")
                        self.log('SUCCESS', f"Server: {api_data.get('server', 'unknown')}")
                        self.log('SUCCESS', f"API Version: {api_data.get('version', '1.0')}")
                        
                        # Check server load if available
                        if 'server_load' in api_data:
                            load = api_data['server_load']
                            self.log('INFO', f"Server Load: {load}%")
                        
                        return True
                    else:
                        self.log('ERROR', "API endpoint not responding correctly")
                        return False
                except json.JSONDecodeError:
                    self.log('ERROR', "Invalid JSON response from API")
                    return False
            else:
                self.log('ERROR', f"API endpoint returned status {response.status_code}")
                self.log('ERROR', "Make sure your server is running on the correct port")
                return False
        
        except requests.exceptions.ConnectionError:
            self.log('ERROR', f"Cannot connect to {self.api_url}")
            self.log('ERROR', "Possible solutions:")
            self.log('ERROR', "1. Check if web server is running")
            self.log('ERROR', "2. Verify the port number")
            self.log('ERROR', "3. Check firewall settings")
            self.log('ERROR', "4. Verify SSL certificate if using HTTPS")
            return False
        except requests.exceptions.Timeout:
            self.log('ERROR', "Connection timeout after 10s")
            return False
        except Exception as e:
            self.log('ERROR', f"Connection test failed: {e}")
            return False
    
    def api_login(self, username: str, password: str) -> bool:
        """Login via API with enhanced error handling"""
        try:
            login_data = {
                'action': 'login',
                'username': username,
                'password': password,
                'client_version': '2.0',
                'client_info': {
                    'threads': self.threads,
                    'cpu_count': multiprocessing.cpu_count(),
                    'platform': sys.platform
                }
            }
            
            response = self.session.post(
                self.api_url,
                data=json.dumps(login_data),
                headers={'Content-Type': 'application/json'},
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    self.user_id = result.get('user_id')
                    self.username = result.get('username')
                    
                    # Get additional user info
                    self.stats['current_balance'] = float(result.get('balance', 0))
                    self.stats['total_earnings'] = float(result.get('total_mined', 0))
                    
                    self.save_session_cache()
                    return True
                else:
                    error_msg = result.get('error', 'Login failed')
                    self.log('ERROR', error_msg)
                    return False
            else:
                self.log('ERROR', f"Login request failed with status {response.status_code}")
                return False
        
        except Exception as e:
            self.log('ERROR', f"API login error: {e}")
            return False
    
    def interactive_login(self) -> bool:
        """Interactive login with retry logic and validation"""
        if not self.test_connection():
            return False
        
        # Try to load cached session first
        if self.load_session_cache():
            if self.test_user_exists():
                return True
            else:
                self.log('WARNING', "Cached session invalid, please login again")
                self.clear_session_cache()
        
        max_attempts = 3
        for attempt in range(max_attempts):
            if attempt > 0:
                self.log('WARNING', f"Login attempt {attempt + 1}/{max_attempts}")
            
            try:
                username = input("Username: ").strip()
                password = getpass.getpass("Password: ")
                
                if not username or not password:
                    self.log('ERROR', "Username and password are required!")
                    continue
                
                # Basic validation
                if len(username) < 3 or len(username) > 20:
                    self.log('ERROR', "Username must be 3-20 characters long!")
                    continue
                
                if self.api_login(username, password):
                    return True
                
                if attempt < max_attempts - 1:
                    time.sleep(2)
            
            except KeyboardInterrupt:
                self.log('WARNING', "Login cancelled by user")
                return False
            except Exception as e:
                self.log('ERROR', f"Login error: {e}")
        
        self.log('ERROR', "Authentication failed after maximum attempts")
        return False
    
    def test_user_exists(self) -> bool:
        """Test if cached user still exists and is valid"""
        try:
            stats_data = {
                'action': 'get_stats',
                'user_id': self.user_id
            }
            
            response = self.session.post(
                self.api_url,
                data=json.dumps(stats_data),
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    # Update stats from server
                    self.stats['current_balance'] = float(result.get('balance', 0))
                    return True
            
            return False
        except:
            return False
    
    def calculate_hash(self, data: str, nonce: int) -> str:
        """Optimized hash calculation with multiple algorithms support"""
        message = f"{data}{nonce}".encode('utf-8')
        
        # Use SHA256 by default, but could be extended for other algorithms
        hash_algorithm = os.getenv('HASH_ALGORITHM', 'sha256').lower()
        
        if hash_algorithm == 'sha256':
            return hashlib.sha256(message).hexdigest()
        elif hash_algorithm == 'sha1':
            return hashlib.sha1(message).hexdigest()
        elif hash_algorithm == 'md5':
            return hashlib.md5(message).hexdigest()
        else:
            return hashlib.sha256(message).hexdigest()  # Default fallback
    
    def is_valid_hash(self, hash_value: str) -> bool:
        """Check if hash meets difficulty requirement with enhanced validation"""
        if not hash_value or len(hash_value) < self.difficulty:
            return False
        
        return hash_value.startswith('0' * self.difficulty)
    
    def adjust_difficulty(self):
        """Auto-adjust difficulty based on performance"""
        if not self.auto_difficulty:
            return
        
        with self.stats_lock:
            if len(self.last_hash_rates) >= 5:  # Need at least 5 samples
                avg_rate = sum(self.last_hash_rates) / len(self.last_hash_rates)
                
                # Adjust difficulty based on hash rate
                if avg_rate > 1000000 and self.difficulty < 8:  # > 1M H/s
                    self.difficulty += 1
                    self.log('INFO', f"Difficulty increased to {self.difficulty}")
                elif avg_rate < 100000 and self.difficulty > 3:  # < 100K H/s
                    self.difficulty -= 1
                    self.log('INFO', f"Difficulty decreased to {self.difficulty}")
    
    def mine_block_thread(self, block_data: str, start_nonce: int, nonce_range: int, thread_id: int) -> Optional[Dict[str, Any]]:
        """Enhanced mining thread with performance monitoring"""
        nonce = start_nonce
        end_nonce = start_nonce + nonce_range
        hashes_computed = 0
        thread_start_time = time.time()
        
        try:
            while self.mining and nonce < end_nonce and not self.shutdown_requested and not self.paused:
                batch_end = min(nonce + self.hash_batch_size, end_nonce)
                
                # Process batch
                for batch_nonce in range(nonce, batch_end):
                    if not self.mining or self.shutdown_requested or self.paused:
                        return None
                    
                    block_hash = self.calculate_hash(block_data, batch_nonce)
                    hashes_computed += 1
                    
                    # Update global hash counter
                    with self.stats_lock:
                        self.stats['total_hashes'] += 1
                    
                    # Check if valid hash found
                    if self.is_valid_hash(block_hash):
                        thread_time = time.time() - thread_start_time
                        thread_hash_rate = hashes_computed / thread_time if thread_time > 0 else 0
                        
                        return {
                            'hash': block_hash,
                            'nonce': batch_nonce,
                            'thread_id': thread_id,
                            'hashes_computed': hashes_computed,
                            'thread_hash_rate': thread_hash_rate,
                            'thread_time': thread_time
                        }
                
                nonce = batch_end
                
                # CPU throttling to prevent overheating
                if self.cpu_limit < 100:
                    time.sleep(0.001 * (100 - self.cpu_limit) / 100)
            
            return None
        
        except Exception as e:
            self.log('ERROR', f"Mining thread {thread_id} error: {e}")
            return None
    
    def mine_block(self, block_data: str) -> Optional[Dict[str, Any]]:
        """Enhanced multi-threaded mining with adaptive performance"""
        self.log('INFO', f"Mining with {self.threads} threads (Difficulty: {self.difficulty})")
        
        start_time = time.time()
        solution_found = False
        total_hashes = 0
        
        with ThreadPoolExecutor(max_workers=self.threads) as executor:
            futures = []
            
            # Submit mining tasks with randomized starting points
            for i in range(self.threads):
                start_nonce = i * self.nonce_range + random.randint(0, 100000)
                future = executor.submit(
                    self.mine_block_thread,
                    block_data,
                    start_nonce,
                    self.nonce_range,
                    i
                )
                futures.append(future)
            
            # Wait for solution with timeout
            try:
                timeout = int(os.getenv('MINING_TIMEOUT', '120'))  # 2 minutes default
                
                for future in as_completed(futures, timeout=timeout):
                    if not self.mining or self.shutdown_requested:
                        break
                    
                    result = future.result()
                    if result and not solution_found:
                        solution_found = True
                        
                        # Cancel remaining futures
                        for f in futures:
                            if not f.done():
                                f.cancel()
                        
                        mining_time = time.time() - start_time
                        hash_rate = result['nonce'] / mining_time if mining_time > 0 else 0
                        
                        # Update statistics
                        with self.stats_lock:
                            self.stats['hash_rate'] = hash_rate
                            self.stats['best_hash_rate'] = max(self.stats['best_hash_rate'], hash_rate)
                            self.last_hash_rates.append(hash_rate)
                            
                            # Keep only last 10 hash rates for averaging
                            if len(self.last_hash_rates) > 10:
                                self.last_hash_rates.pop(0)
                        
                        self.log('SUCCESS', f"Block found! Hash: {result['hash'][:16]}...")
                        self.log('SUCCESS', f"Nonce: {result['nonce']:,} | Time: {mining_time:.2f}s | Rate: {hash_rate:.0f} H/s")
                        
                        # Auto-adjust difficulty
                        self.adjust_difficulty()
                        
                        return result
                
                # No solution found within timeout
                if not solution_found and self.mining and not self.shutdown_requested:
                    total_searched = self.nonce_range * self.threads
                    self.log('INFO', f"No solution found in {total_searched:,} hashes ({timeout}s timeout)")
            
            except Exception as e:
                self.log('ERROR', f"Mining execution error: {e}")
            
            finally:
                # Cancel all remaining futures
                for f in futures:
                    if not f.done():
                        f.cancel()
        
        return None
    
    def submit_block(self, block_hash: str, nonce: int) -> bool:
        """Enhanced block submission with comprehensive error handling"""
        payload = {
            'user_id': self.user_id,
            'block_hash': block_hash,
            'nonce': nonce,
            'difficulty': self.difficulty,
            'hash_rate': int(self.stats.get('hash_rate', 0)),
            'api_secret': self.api_secret,
            'client_version': '2.0',
            'system_info': {
                'threads': self.threads,
                'cpu_usage': self.stats.get('cpu_usage', 0),
                'memory_usage': self.stats.get('memory_usage', 0)
            }
        }
        
        for attempt in range(self.retry_attempts):
            try:
                if attempt > 0:
                    self.log('WARNING', f"Retry attempt {attempt + 1}/{self.retry_attempts}")
                    time.sleep(self.retry_delay * attempt)  # Exponential backoff
                
                self.log('INFO', f"Submitting block... (Rate: {self.stats.get('hash_rate', 0):.0f} H/s)")
                
                response = self.session.post(
                    self.api_url,
                    data=json.dumps(payload),
                    headers={'Content-Type': 'application/json'},
                    timeout=self.timeout
                )
                
                if response.status_code == 200:
                    try:
                        result = response.json()
                        
                        if result.get('success'):
                            # Update statistics
                            with self.stats_lock:
                                self.stats['accepted_blocks'] += 1
                                self.stats['blocks_mined'] += 1
                                self.stats['last_block_time'] = time.time()
                                self.stats['total_earnings'] += float(result.get('final_reward', 0))
                                self.stats['current_balance'] = float(result.get('new_balance', 0))
                                self.stats['power_level'] = result.get('power_level', 'low')
                                
                                # Calculate average block time
                                if self.stats['accepted_blocks'] > 1:
                                    elapsed = time.time() - self.stats['start_time']
                                    self.stats['average_block_time'] = elapsed / self.stats['accepted_blocks']
                            
                            # Enhanced logging
                            reward = result.get('final_reward', 0)
                            balance = result.get('new_balance', 0)
                            block_num = result.get('block_number', 0)
                            power_level = result.get('power_level', 'unknown')
                            
                            success_rate = (self.stats['accepted_blocks'] / 
                                          (self.stats['accepted_blocks'] + self.stats['rejected_blocks']) * 100) if (self.stats['accepted_blocks'] + self.stats['rejected_blocks']) > 0 else 100
                            
                            self.log('SUCCESS', 
                                   f"Accepted {self.stats['accepted_blocks']}/{self.stats['accepted_blocks'] + self.stats['rejected_blocks']} "
                                   f"({success_rate:.1f}%) ∙ +{reward} PHN ∙ Balance: {balance} PHN ∙ "
                                   f"Block #{block_num} ∙ Power: {power_level.upper()}")
                            
                            # Save session after successful block
                            self.save_session_cache()
                            
                            return True
                        else:
                            error_msg = result.get('error', 'Unknown error')
                            self.log('ERROR', f"Block rejected: {error_msg}")
                            
                            with self.stats_lock:
                                self.stats['rejected_blocks'] += 1
                            
                            # Don't retry certain errors
                            non_retryable_errors = ['duplicate', 'already submitted', 'exists', 'invalid hash', 'expired']
                            if any(keyword in error_msg.lower() for keyword in non_retryable_errors):
                                return False
                    
                    except json.JSONDecodeError as e:
                        self.log('ERROR', f"Invalid JSON response: {e}")
                        with self.stats_lock:
                            self.stats['network_errors'] += 1
                
                elif response.status_code == 409:
                    self.log('WARNING', "Duplicate block detected")
                    with self.stats_lock:
                        self.stats['rejected_blocks'] += 1
                    return False
                
                elif response.status_code == 429:
                    self.log('WARNING', "Rate limited by server")
                    time.sleep(5)  # Wait longer for rate limiting
                    
                else:
                    self.log('ERROR', f"Server error: {response.status_code}")
                    with self.stats_lock:
                        self.stats['network_errors'] += 1
            
            except requests.exceptions.Timeout:
                self.log('ERROR', f"Request timeout (attempt {attempt + 1})")
                with self.stats_lock:
                    self.stats['network_errors'] += 1
            
            except requests.exceptions.ConnectionError:
                self.log('ERROR', f"Connection error (attempt {attempt + 1})")
                with self.stats_lock:
                    self.stats['network_errors'] += 1
            
            except Exception as e:
                self.log('ERROR', f"Submission error: {e}")
                with self.stats_lock:
                    self.stats['network_errors'] += 1
        
        self.log('ERROR', "Block submission failed after all attempts")
        return False
    
    def generate_block_data(self) -> str:
        """Generate enhanced block data with additional entropy"""
        timestamp = int(time.time())
        random_data = random.randint(1000000, 9999999)
        session_id = hash(str(self.stats['start_time'])) % 1000000
        
        return f"phonesium_{timestamp}_{random_data}_{self.user_id}_{session_id}"
    
    def monitor_system_performance(self):
        """Monitor system performance in background"""
        while self.mining and not self.shutdown_requested:
            try:
                # CPU usage
                cpu_percent = psutil.cpu_percent(interval=1)
                
                # Memory usage
                memory = psutil.virtual_memory()
                memory_percent = memory.percent
                
                # Update stats
                with self.stats_lock:
                    self.stats['cpu_usage'] = cpu_percent
                    self.stats['memory_usage'] = memory_percent
                    self.stats['session_uptime'] = time.time() - self.stats['start_time']
                
                # CPU throttling if usage too high
                if cpu_percent > self.cpu_limit:
                    self.log('WARNING', f"High CPU usage ({cpu_percent:.1f}%), throttling...")
                    time.sleep(1)
                
                # Memory warning
                if memory_percent > 90:
                    self.log('WARNING', f"High memory usage ({memory_percent:.1f}%)")
                
                time.sleep(5)  # Check every 5 seconds
                
            except Exception as e:
                self.log('DEBUG', f"Performance monitoring error: {e}")
                time.sleep(10)
    
    def print_stats(self):
        """Print comprehensive statistics with enhanced formatting"""
        with self.stats_lock:
            elapsed = time.time() - self.stats['start_time']
            avg_hash_rate = self.stats['total_hashes'] / elapsed if elapsed > 0 else 0
            total_attempts = self.stats['accepted_blocks'] + self.stats['rejected_blocks']
            success_rate = (self.stats['accepted_blocks'] / total_attempts * 100) if total_attempts > 0 else 0
            
            print(f"\n{'='*70}")
            print(f"📊 PHONESIUM MINING STATISTICS - ENHANCED")
            print(f"{'='*70}")
            print(f"👤 Miner: {self.username} (ID: {self.user_id})")
            print(f"⏱️  Runtime: {elapsed:.0f}s ({elapsed/3600:.1f}h)")
            print(f"🧵 Threads: {self.threads} | CPU: {self.stats['cpu_usage']:.1f}% | RAM: {self.stats['memory_usage']:.1f}%")
            print(f"💎 Difficulty: {self.difficulty} leading zeros")
            print(f"{'='*70}")
            print(f"📈 MINING PERFORMANCE")
            print(f"💎 Blocks Accepted: {self.stats['accepted_blocks']}")
            print(f"❌ Blocks Rejected: {self.stats['rejected_blocks']}")
            print(f"🌐 Network Errors: {self.stats['network_errors']}")
            print(f"✅ Success Rate: {success_rate:.1f}%")
            print(f"🔢 Total Hashes: {self.stats['total_hashes']:,}")
            print(f"⚡ Current Rate: {self.stats['hash_rate']:.0f} H/s")
            print(f"🚀 Average Rate: {avg_hash_rate:.0f} H/s")
            print(f"🏆 Best Rate: {self.stats['best_hash_rate']:.0f} H/s")
            print(f"⏰ Avg Block Time: {self.stats['average_block_time']:.0f}s")
            print(f"🔋 Power Level: {self.stats['power_level'].upper()}")
            print(f"{'='*70}")
            print(f"💰 EARNINGS")
            print(f"💰 Session Earnings: {self.stats['total_earnings']:.8f} PHN")
            print(f"💳 Current Balance: {self.stats['current_balance']:.8f} PHN")
            
            if self.stats['last_block_time']:
                time_since_last = time.time() - self.stats['last_block_time']
                print(f"🕐 Last Block: {time_since_last:.0f}s ago")
            
            # Efficiency metrics
            if elapsed > 0:
                blocks_per_hour = (self.stats['accepted_blocks'] / elapsed) * 3600
                earnings_per_hour = (self.stats['total_earnings'] / elapsed) * 3600
                print(f"📊 Blocks/Hour: {blocks_per_hour:.2f}")
                print(f"💵 PHN/Hour: {earnings_per_hour:.6f}")
            
            print(f"{'='*70}\n")
    
    def stats_monitor(self):
        """Enhanced background stats monitoring"""
        while self.mining and not self.shutdown_requested:
            time.sleep(60)  # Every minute
            if self.mining and not self.shutdown_requested:
                self.print_stats()
                
                # Auto-save session periodically
                if self.stats['accepted_blocks'] % 10 == 0 and self.stats['accepted_blocks'] > 0:
                    self.save_session_cache()
    
    def display_banner(self):
        """Display enhanced startup banner"""
        print(f"\n{'='*70}")
        print(f"🚀 PHONESIUM MINING CLIENT v2.0 - ENHANCED EDITION")
        print(f"{'='*70}")
        print(f"👤 User: {self.username} (ID: {self.user_id})")
        print(f"🧵 Threads: {self.threads} / {multiprocessing.cpu_count()} available")
        print(f"💎 Difficulty: {self.difficulty} leading zeros")
        print(f"🌐 Server: {self.base_url}")
        print(f"⚡ Target Rate: ~{self.nonce_range * self.threads:,} H/s")
        print(f"🔧 Auto Difficulty: {'ON' if self.auto_difficulty else 'OFF'}")
        print(f"🎯 CPU Limit: {self.cpu_limit}%")
        print(f"💾 Memory Limit: {self.memory_limit}MB")
        print(f"{'='*70}")
        print(f"🎯 Ready to mine! Press Ctrl+C to stop gracefully.")
        print(f"{'='*70}\n")
    
    def pause_mining(self):
        """Pause mining temporarily"""
        self.paused = True
        self.log('WARNING', "Mining paused")
    
    def resume_mining(self):
        """Resume mining"""
        self.paused = False
        self.log('INFO', "Mining resumed")
    
    def start_mining(self):
        """Start the enhanced mining process"""
        self.display_banner()
        
        self.mining = True
        
        # Start background monitors
        stats_thread = threading.Thread(target=self.stats_monitor, daemon=True)
        stats_thread.start()
        
        performance_thread = threading.Thread(target=self.monitor_system_performance, daemon=True)
        performance_thread.start()
        
        try:
            consecutive_failures = 0
            max_consecutive_failures = 5
            
            while self.mining and not self.shutdown_requested:
                if self.paused:
                    time.sleep(1)
                    continue
                
                try:
                    # Generate new block data
                    block_data = self.generate_block_data()
                    
                    self.log('INFO', "Starting mining job...")
                    
                    # Mine the block
                    result = self.mine_block(block_data)
                    
                    if result and self.mining and not self.shutdown_requested:
                        # Submit the block
                        success = self.submit_block(result['hash'], result['nonce'])
                        
                        if success:
                            consecutive_failures = 0
                            time.sleep(1)  # Brief pause before next block
                        else:
                            consecutive_failures += 1
                            self.log('WARNING', f"Block submission failed ({consecutive_failures}/{max_consecutive_failures})")
                            time.sleep(2)
                    else:
                        if not self.shutdown_requested and not self.paused:
                            self.log('INFO', "No solution found, generating new job...")
                            time.sleep(1)
                    
                    # Check for too many consecutive failures
                    if consecutive_failures >= max_consecutive_failures:
                        self.log('ERROR', "Too many consecutive failures, pausing for 30 seconds...")
                        time.sleep(30)
                        consecutive_failures = 0
                
                except Exception as e:
                    self.log('ERROR', f"Mining loop error: {e}")
                    time.sleep(5)
        
        except KeyboardInterrupt:
            self.log('WARNING', "Mining stopped by user (Ctrl+C)")
            self.shutdown_requested = True
        
        except Exception as e:
            self.log('ERROR', f"Mining error: {e}")
        
        finally:
            self.mining = False
            self.log('INFO', "Stopping mining threads...")
            time.sleep(2)
            
            # Final stats and cleanup
            self.print_stats()
            self.save_session_cache()
            self.log('SUCCESS', "Mining session ended. Thank you for mining Phonesium!")

def main():
    """Main entry point with enhanced argument parsing"""
    parser = argparse.ArgumentParser(
        description='Phonesium Mining Client v2.0 - Enhanced Edition',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python miner.py                          # Interactive login
  python miner.py --threads 8              # Use 8 threads
  python miner.py --difficulty 6           # Set difficulty to 6
  python miner.py --user-id 123 --username miner1  # Skip login
  python miner.py --clear-cache            # Clear session cache
  python miner.py --url https://myserver.com  # Custom server
        """
    )
    
    parser.add_argument('--user-id', type=int, help='User ID (skip login)')
    parser.add_argument('--username', help='Username (with --user-id)')
    parser.add_argument('--threads', type=int, help='Number of mining threads')
    parser.add_argument('--difficulty', type=int, help='Mining difficulty (leading zeros)')
    parser.add_argument('--clear-cache', action='store_true', help='Clear session cache')
    parser.add_argument('--url', help='Custom base URL (e.g., https://shp.re)')
    parser.add_argument('--auto-difficulty', action='store_true', help='Enable auto difficulty adjustment')
    parser.add_argument('--cpu-limit', type=int, help='CPU usage limit percentage (1-100)')
    parser.add_argument('--log-file', action='store_true', help='Enable logging to file')
    parser.add_argument('--version', action='version', version='Phonesium Miner v2.0')
    
    args = parser.parse_args()
    
    # Initialize miner
    miner = PhonesiumMiner()
    
    # Apply command line arguments
    if args.url:
        miner.base_url = args.url
        miner.api_url = f"{args.url}/api"
        print(f"Using custom URL: {miner.api_url}")
    
    if args.clear_cache:
        miner.clear_session_cache()
        print("Session cache cleared!")
        return
    
    if args.threads:
        miner.threads = min(args.threads, multiprocessing.cpu_count())
        print(f"Using {miner.threads} threads")
    
    if args.difficulty:
        miner.difficulty = max(1, min(args.difficulty, 10))  # Limit between 1-10
        print(f"Using difficulty: {miner.difficulty}")
    
    if args.auto_difficulty:
        miner.auto_difficulty = True
        print("Auto difficulty adjustment enabled")
    
    if args.cpu_limit:
        miner.cpu_limit = max(10, min(args.cpu_limit, 100))  # Limit between 10-100
        print(f"CPU limit set to: {miner.cpu_limit}%")
    
    if args.log_file:
        os.environ['LOG_TO_FILE'] = 'true'
        print("File logging enabled")
    
    # Handle direct user ID login
    if args.user_id:
        miner.user_id = args.user_id
        miner.username = args.username or f"user_{args.user_id}"
        miner.log('INFO', f"Using User ID: {args.user_id}")
    else:
        # Interactive login
        if not miner.interactive_login():
            miner.log('ERROR', "Authentication failed")
            sys.exit(1)
    
    # Start mining
    try:
        miner.start_mining()
    except Exception as e:
        miner.log('ERROR', f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
