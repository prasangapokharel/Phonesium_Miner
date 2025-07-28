#!/usr/bin/env python3
"""
Phonesium Mining Client - Fixed for port 8000
Like Duino-Coin but for Phonesium
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

# Load environment variables
load_dotenv()

class PhonesiumMiner:
    def __init__(self):
        # Configuration - Fixed for port 8000
        self.base_url = os.getenv('BASE_URL', 'https://shp.re')
        self.api_url = f"{self.base_url}/api.php"
        
        # Mining settings
        self.difficulty = int(os.getenv('DIFFICULTY', 5))
        self.api_secret = os.getenv('API_SECRET', 'TTXRESS2')
        self.timeout = int(os.getenv('TIMEOUT', 30))
        self.retry_attempts = int(os.getenv('RETRY_ATTEMPTS', 5))
        self.retry_delay = int(os.getenv('RETRY_DELAY', 2))
        
        # Performance settings
        self.threads = min(int(os.getenv('THREADS', 4)), multiprocessing.cpu_count())
        self.nonce_range = int(os.getenv('NONCE_RANGE', 1000000))  # Reduced for better completion
        self.hash_batch_size = int(os.getenv('HASH_BATCH_SIZE', 10000))  # Smaller batches
        
        # Session cache file
        self.cache_file = 'phonesium_session.cache'
        
        # Session with better configuration
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Phonesium-Miner/1.0',
            'Accept': 'application/json',
            'Connection': 'keep-alive'
        })
        
        # Add connection pooling
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            max_retries=3
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        
        self.user_id = None
        self.username = None
        self.mining = False
        self.shutdown_requested = False
        
        # Enhanced stats
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
            'current_balance': 0.0
        }
        self.stats_lock = threading.Lock()

    def log(self, level, message, thread_id=None):
        """Enhanced logging like Duino-Coin"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        thread_prefix = f"cpu{thread_id}" if thread_id is not None else "sys0"
        
        # Color coding
        colors = {
            'SUCCESS': '\033[92m',  # Green
            'ERROR': '\033[91m',    # Red
            'WARNING': '\033[93m',  # Yellow
            'INFO': '\033[94m',     # Blue
            'RESET': '\033[0m'      # Reset
        }
        
        color = colors.get(level, colors['RESET'])
        print(f"{color}{timestamp}  {thread_prefix}  {message}{colors['RESET']}")

    def save_session_cache(self):
        """Save session data to cache file"""
        try:
            cache_data = {
                'user_id': self.user_id,
                'username': self.username,
                'timestamp': time.time()
            }
            with open(self.cache_file, 'wb') as f:
                pickle.dump(cache_data, f)
            self.log('INFO', f"Session cached for user: {self.username}")
        except Exception as e:
            self.log('WARNING', f"Failed to save session cache: {e}")

    def load_session_cache(self):
        """Load session data from cache file"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'rb') as f:
                    cache_data = pickle.load(f)
                
                # Check if cache is not too old (24 hours)
                if time.time() - cache_data.get('timestamp', 0) < 86400:
                    self.user_id = cache_data.get('user_id')
                    self.username = cache_data.get('username')
                    
                    if self.user_id and self.username:
                        self.log('SUCCESS', f"Loaded cached session: {self.username} (ID: {self.user_id})")
                        return True
                else:
                    self.log('INFO', "Session cache expired")
                    os.remove(self.cache_file)
        except Exception as e:
            self.log('WARNING', f"Failed to load session cache: {e}")
            if os.path.exists(self.cache_file):
                os.remove(self.cache_file)
        
        return False

    def clear_session_cache(self):
        """Clear session cache"""
        try:
            if os.path.exists(self.cache_file):
                os.remove(self.cache_file)
                self.log('INFO', "Session cache cleared")
        except Exception as e:
            self.log('WARNING', f"Failed to clear session cache: {e}")

    def test_connection(self):
        """Test server connection with detailed feedback"""
        self.log('INFO', f"Testing connection to {self.api_url}...")
        
        try:
            # Test API endpoint directly
            start_time = time.time()
            response = self.session.get(self.api_url, timeout=10)
            response_time = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                try:
                    api_data = response.json()
                    if api_data.get('status') == 'online':
                        self.log('SUCCESS', f"API endpoint online (Response: {response_time:.0f}ms)")
                        self.log('SUCCESS', f"Server: {api_data.get('server', 'unknown')}")
                        self.log('SUCCESS', f"API Version: {api_data.get('version', 'unknown')}")
                        return True
                    else:
                        self.log('ERROR', "API endpoint not responding correctly")
                        return False
                except json.JSONDecodeError:
                    self.log('ERROR', "Invalid JSON response from API")
                    return False
            else:
                self.log('ERROR', f"API endpoint returned status {response.status_code}")
                self.log('ERROR', f"Make sure your server is running on the correct port")
                return False
                
        except requests.exceptions.ConnectionError:
            self.log('ERROR', f"Cannot connect to {self.api_url}")
            self.log('ERROR', "Possible solutions:")
            self.log('ERROR', "1. Check if web server is running")
            self.log('ERROR', "2. Verify the port number (8000 vs 80)")
            self.log('ERROR', "3. Check the folder name case (Phonesium vs phonesium)")
            return False
        except requests.exceptions.Timeout:
            self.log('ERROR', f"Connection timeout after 10s")
            return False
        except Exception as e:
            self.log('ERROR', f"Connection test failed: {e}")
            return False

    def api_login(self, username, password):
        """Login via API"""
        try:
            login_data = {
                'action': 'login',
                'username': username,
                'password': password
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
                    self.save_session_cache()
                    return True
                else:
                    self.log('ERROR', result.get('error', 'Login failed'))
                    return False
            else:
                self.log('ERROR', f"Login request failed with status {response.status_code}")
                return False
                
        except Exception as e:
            self.log('ERROR', f"API login error: {e}")
            return False

    def interactive_login(self):
        """Interactive login with retry logic"""
        if not self.test_connection():
            return False
        
        # Try to load cached session first
        if self.load_session_cache():
            # Verify cached session is still valid
            if self.test_user_exists():
                return True
            else:
                self.log('WARNING', "Cached session invalid, please login again")
                self.clear_session_cache()
        
        max_attempts = 3
        for attempt in range(max_attempts):
            if attempt > 0:
                self.log('WARNING', f"Login attempt {attempt + 1}/{max_attempts}")
            
            username = input("Username: ").strip()
            password = getpass.getpass("Password: ")
            
            if not username or not password:
                self.log('ERROR', "Username and password are required!")
                continue
            
            if self.api_login(username, password):
                return True
            
            if attempt < max_attempts - 1:
                time.sleep(2)
        
        self.log('ERROR', "Authentication failed after maximum attempts")
        return False

    def test_user_exists(self):
        """Test if cached user still exists"""
        try:
            # Try to get user stats to verify user exists
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
                return result.get('success', False)
            
            return False
        except:
            return False

    def calculate_hash(self, data, nonce):
        """Optimized hash calculation"""
        message = f"{data}{nonce}".encode('utf-8')
        return hashlib.sha256(message).hexdigest()

    def is_valid_hash(self, hash_value):
        """Check if hash meets difficulty requirement"""
        return hash_value.startswith('0' * self.difficulty)

    def mine_block_thread(self, block_data, start_nonce, nonce_range, thread_id):
        """Fixed mining thread with proper completion handling"""
        nonce = start_nonce
        end_nonce = start_nonce + nonce_range
        hashes_computed = 0
        
        try:
            while self.mining and nonce < end_nonce and not self.shutdown_requested:
                batch_end = min(nonce + self.hash_batch_size, end_nonce)
                
                for batch_nonce in range(nonce, batch_end):
                    if not self.mining or self.shutdown_requested:
                        return None
                    
                    block_hash = self.calculate_hash(block_data, batch_nonce)
                    hashes_computed += 1
                    
                    with self.stats_lock:
                        self.stats['total_hashes'] += 1
                    
                    if self.is_valid_hash(block_hash):
                        return {
                            'hash': block_hash,
                            'nonce': batch_nonce,
                            'thread_id': thread_id,
                            'hashes_computed': hashes_computed
                        }
                
                nonce = batch_end
                
                # Small delay to prevent CPU overload
                time.sleep(0.001)
            
            return None
            
        except Exception as e:
            self.log('ERROR', f"Mining thread {thread_id} error: {e}")
            return None

    def mine_block(self, block_data):
        """Fixed multi-threaded mining with proper completion"""
        self.log('INFO', f"Mining with {self.threads} threads (Difficulty: {self.difficulty})")
        
        start_time = time.time()
        solution_found = False
        
        with ThreadPoolExecutor(max_workers=self.threads) as executor:
            futures = []
            
            # Submit mining tasks
            for i in range(self.threads):
                start_nonce = i * self.nonce_range + random.randint(0, 10000)
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
                for future in as_completed(futures, timeout=60):  # 60 second timeout
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
                        
                        self.log('SUCCESS', f"Block found! Hash: {result['hash'][:16]}...")
                        self.log('SUCCESS', f"Nonce: {result['nonce']:,} | Time: {mining_time:.2f}s | Rate: {hash_rate:.0f} H/s")
                        
                        with self.stats_lock:
                            self.stats['hash_rate'] = hash_rate
                        
                        return result
                
                # If we get here, no solution was found
                if not solution_found and self.mining and not self.shutdown_requested:
                    self.log('INFO', f"No solution found in {self.nonce_range * self.threads:,} hashes")
                
            except Exception as e:
                self.log('ERROR', f"Mining execution error: {e}")
                # Cancel all futures
                for f in futures:
                    if not f.done():
                        f.cancel()
        
        return None

    def submit_block(self, block_hash, nonce):
        """Enhanced block submission with robust error handling"""
        payload = {
            'user_id': self.user_id,
            'block_hash': block_hash,
            'nonce': nonce,
            'difficulty': self.difficulty,
            'hash_rate': int(self.stats.get('hash_rate', 0)),
            'api_secret': self.api_secret
        }
        
        for attempt in range(self.retry_attempts):
            try:
                if attempt > 0:
                    self.log('WARNING', f"Retry attempt {attempt + 1}/{self.retry_attempts}")
                    time.sleep(self.retry_delay)
                
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
                            with self.stats_lock:
                                self.stats['accepted_blocks'] += 1
                                self.stats['blocks_mined'] += 1
                                self.stats['last_block_time'] = time.time()
                                self.stats['total_earnings'] += float(result.get('final_reward', 0))
                                self.stats['current_balance'] = float(result.get('new_balance', 0))
                            
                            # Log like Duino-Coin
                            reward = result.get('final_reward', 0)
                            balance = result.get('new_balance', 0)
                            block_num = result.get('block_number', 0)
                            power_level = result.get('power_level', 'unknown')
                            
                            self.log('SUCCESS', f"Accepted {self.stats['accepted_blocks']}/{self.stats['accepted_blocks'] + self.stats['rejected_blocks']} (100%) ∙ +{reward} PHN ∙ Balance: {balance} PHN ∙ Block #{block_num} ∙ Power: {power_level.upper()}")
                            
                            return True
                        else:
                            error_msg = result.get('error', 'Unknown error')
                            self.log('ERROR', f"Block rejected: {error_msg}")
                            
                            with self.stats_lock:
                                self.stats['rejected_blocks'] += 1
                            
                            # Don't retry certain errors
                            if any(keyword in error_msg.lower() for keyword in ['duplicate', 'already submitted', 'exists']):
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

    def generate_block_data(self):
        """Generate block data for mining"""
        timestamp = int(time.time())
        random_data = random.randint(1000000, 9999999)
        return f"phonesium_{timestamp}_{random_data}_{self.user_id}"

    def print_stats(self):
        """Print comprehensive statistics like Duino-Coin"""
        with self.stats_lock:
            elapsed = time.time() - self.stats['start_time']
            avg_hash_rate = self.stats['total_hashes'] / elapsed if elapsed > 0 else 0
            total_attempts = self.stats['accepted_blocks'] + self.stats['rejected_blocks']
            success_rate = (self.stats['accepted_blocks'] / total_attempts * 100) if total_attempts > 0 else 0
            
            print(f"\n{'='*60}")
            print(f"📊 PHONESIUM MINING STATISTICS")
            print(f"{'='*60}")
            print(f"⏱️  Runtime: {elapsed:.0f}s ({elapsed/3600:.1f}h)")
            print(f"💎 Blocks Accepted: {self.stats['accepted_blocks']}")
            print(f"❌ Blocks Rejected: {self.stats['rejected_blocks']}")
            print(f"🌐 Network Errors: {self.stats['network_errors']}")
            print(f"✅ Success Rate: {success_rate:.1f}%")
            print(f"🔢 Total Hashes: {self.stats['total_hashes']:,}")
            print(f"⚡ Average Rate: {avg_hash_rate:.0f} H/s")
            print(f"🧵 Threads: {self.threads}")
            print(f"💰 Total Earnings: {self.stats['total_earnings']:.8f} PHN")
            print(f"💳 Current Balance: {self.stats['current_balance']:.8f} PHN")
            
            if self.stats['last_block_time']:
                time_since_last = time.time() - self.stats['last_block_time']
                print(f"🕐 Last Block: {time_since_last:.0f}s ago")
            
            print(f"{'='*60}\n")

    def stats_monitor(self):
        """Background stats monitoring"""
        while self.mining and not self.shutdown_requested:
            time.sleep(60)  # Every minute like Duino-Coin
            if self.mining and not self.shutdown_requested:
                self.print_stats()

    def display_banner(self):
        """Display startup banner like Duino-Coin"""
        print(f"\n{'='*60}")
        print(f"🚀 PHONESIUM MINING CLIENT v1.0")
        print(f"{'='*60}")
        print(f"👤 User: {self.username} (ID: {self.user_id})")
        print(f"🧵 Threads: {self.threads}")
        print(f"💎 Difficulty: {self.difficulty} leading zeros")
        print(f"🌐 Server: {self.base_url}")
        print(f"⚡ Target Rate: ~250K H/s")
        print(f"{'='*60}")
        print(f"Have a productive mining session!")
        print(f"{'='*60}\n")

    def start_mining(self):
        """Start the mining process with enhanced monitoring"""
        self.display_banner()
        
        self.mining = True
        
        # Start stats monitor
        stats_thread = threading.Thread(target=self.stats_monitor, daemon=True)
        stats_thread.start()
        
        try:
            while self.mining and not self.shutdown_requested:
                block_data = self.generate_block_data()
                
                self.log('INFO', f"Starting mining job...")
                
                result = self.mine_block(block_data)
                
                if result and self.mining and not self.shutdown_requested:
                    success = self.submit_block(result['hash'], result['nonce'])
                    
                    if success:
                        # Brief pause before next block
                        time.sleep(1)
                    else:
                        self.log('WARNING', "Block submission failed, generating new job...")
                        time.sleep(2)
                else:
                    if not self.shutdown_requested:
                        self.log('INFO', "No solution found, generating new job...")
                        time.sleep(1)
        
        except KeyboardInterrupt:
            self.log('WARNING', "Mining stopped by user (Ctrl+C)")
            self.shutdown_requested = True
        except Exception as e:
            self.log('ERROR', f"Mining error: {e}")
        finally:
            self.mining = False
            self.log('INFO', "Stopping mining threads...")
            time.sleep(2)
            self.print_stats()
            self.log('SUCCESS', f"Mining session ended. Thank you for mining Phonesium!")

def main():
    parser = argparse.ArgumentParser(description='Phonesium Mining Client')
    parser.add_argument('--user-id', type=int, help='User ID (skip login)')
    parser.add_argument('--username', help='Username (with --user-id)')
    parser.add_argument('--threads', type=int, help='Number of threads')
    parser.add_argument('--difficulty', type=int, help='Mining difficulty')
    parser.add_argument('--clear-cache', action='store_true', help='Clear session cache')
    parser.add_argument('--url', help='Custom base URL (e.g., https://shp.re)')
    
    args = parser.parse_args()
    
    miner = PhonesiumMiner()
    
    # Override URL if provided
    if args.url:
        miner.base_url = args.url
        miner.api_url = f"{args.url}/api.php"
        print(f"Using custom URL: {miner.api_url}")
    
    # Clear cache if requested
    if args.clear_cache:
        miner.clear_session_cache()
        print("Session cache cleared!")
        return
    
    # Override settings
    if args.threads:
        miner.threads = min(args.threads, multiprocessing.cpu_count())
    if args.difficulty:
        miner.difficulty = args.difficulty
    
    if args.user_id:
        miner.user_id = args.user_id
        miner.username = args.username or f"user_{args.user_id}"
        miner.log('INFO', f"Using User ID: {args.user_id}")
    else:
        if not miner.interactive_login():
            miner.log('ERROR', "Authentication failed")
            sys.exit(1)
    
    miner.start_mining()

if __name__ == "__main__":
    main()
