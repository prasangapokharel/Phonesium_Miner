import argparse
import sys
import time
import threading
import multiprocessing
from dotenv import load_dotenv

# Import refactored modules using absolute imports from the 'miner' package
from miner.config import MinerConfig
from miner.logger import Logger
from miner.session_manager import SessionManager
from miner.api_handler import ApiHandler
from miner.miner_core import MinerCore
from miner.stats_monitor import StatsMonitor

# Load environment variables at the very beginning
load_dotenv()

class PhonesiumMinerApp:
    """Main application class for the Phonesium Miner."""
    def __init__(self):
        self.config = MinerConfig()
        self.logger = Logger()
        self.session_manager = SessionManager(self.config, self.logger)
        self.api_handler = ApiHandler(self.config, self.logger, self.session_manager)
        
        # Shared mining state and statistics
        self.user_id = None
        self.username = None
        self.mining = False
        self.shutdown_requested = False
        self.paused = False
        
        self.stats = {
            'user_id': None,
            'username': None,
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
            'temperature': 0, # Placeholder, requires platform-specific libraries
            'power_level': 'low',
            'session_uptime': 0
        }
        self.stats_lock = threading.Lock() # Protects access to self.stats
        
        self.miner_core = MinerCore(self.config, self.logger, self.stats_lock, self.stats)
        self.stats_monitor = StatsMonitor(self.config, self.logger, self.stats_lock, self.stats)

        # Signal handlers for graceful shutdown
        import signal
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        self.logger.log('WARNING', f"Received signal {signum}, initiating graceful shutdown...")
        self.shutdown_requested = True
        self.mining = False
        self.miner_core.shutdown_requested = True
        self.stats_monitor.running = False

    def display_banner(self):
        """Displays the miner's startup banner."""
        with self.stats_lock: # Ensure stats are consistent when printing banner
            print(f"\n{'='*70}")
            print(f"🚀 PHONESIUM MINING CLIENT v2.0 - ENHANCED EDITION")
            print(f"{'='*70}")
            print(f"👤 User: {self.username} (ID: {self.user_id})")
            print(f"🧵 Threads: {self.config.threads} / {multiprocessing.cpu_count()} available")
            print(f"💎 Difficulty: {self.config.difficulty} leading zeros")
            print(f"🌐 Server: {self.config.base_url}")
            print(f"⚡ Target Rate: ~{self.config.nonce_range * self.config.threads:,} H/s")
            print(f"🔧 Auto Difficulty: {'ON' if self.config.auto_difficulty else 'OFF'}")
            print(f"🎯 CPU Limit: {self.config.cpu_limit}%")
            print(f"💾 Memory Limit: {self.config.memory_limit}MB")
            print(f"{'='*70}")
            print(f"🎯 Ready to mine! Press Ctrl+C to stop gracefully.")
            print(f"{'='*70}\n")

    def interactive_login(self) -> bool:
        """Handles interactive user login with cache and retries."""
        if not self.api_handler.test_connection():
            return False
        
        # Try to load cached session first
        cached_data = self.session_manager.load_session_cache()
        if cached_data:
            user_id = cached_data.get('user_id')
            username = cached_data.get('username')
            if user_id and username:
                user_check = self.api_handler.test_user_exists(user_id)
                if user_check.get('success'):
                    self.user_id = user_id
                    self.username = username
                    with self.stats_lock:
                        self.stats['user_id'] = user_id
                        self.stats['username'] = username
                        self.stats['current_balance'] = cached_data.get('stats', {}).get('current_balance', user_check.get('balance', 0.0))
                        self.stats['total_earnings'] = cached_data.get('stats', {}).get('total_earnings', 0.0)
                    return True
                else:
                    self.logger.log('WARNING', "Cached session invalid or user no longer exists, please login again.")
                    self.session_manager.clear_session_cache()
        
        max_attempts = 3
        for attempt in range(max_attempts):
            if attempt > 0:
                self.logger.log('WARNING', f"Login attempt {attempt + 1}/{max_attempts}")
            
            try:
                username_input = input("Username: ").strip()
                import getpass
                password_input = getpass.getpass("Password: ")
                
                if not username_input or not password_input:
                    self.logger.log('ERROR', "Username and password are required!")
                    continue
                
                if len(username_input) < 3 or len(username_input) > 20:
                    self.logger.log('ERROR', "Username must be 3-20 characters long!")
                    continue
                
                login_result = self.api_handler.api_login(username_input, password_input)
                if login_result.get('success'):
                    self.user_id = login_result['user_id']
                    self.username = login_result['username']
                    with self.stats_lock:
                        self.stats['user_id'] = self.user_id
                        self.stats['username'] = self.username
                        self.stats['current_balance'] = login_result.get('balance', 0.0)
                        self.stats['total_earnings'] = login_result.get('total_mined', 0.0)
                    self.session_manager.save_session_cache(self.user_id, self.username, self.stats)
                    return True
                
                if attempt < max_attempts - 1:
                    time.sleep(2)
            except KeyboardInterrupt:
                self.logger.log('WARNING', "Login cancelled by user")
                return False
            except Exception as e:
                self.logger.log('ERROR', f"Login error: {e}")
        self.logger.log('ERROR', "Authentication failed after maximum attempts")
        return False

    def pause_mining(self):
        """Pauses the mining process."""
        self.paused = True
        self.miner_core.paused = True
        self.logger.log('WARNING', "Mining paused")

    def resume_mining(self):
        """Resumes the mining process."""
        self.paused = False
        self.miner_core.paused = False
        self.logger.log('INFO', "Mining resumed")

    def start_mining(self):
        """Starts the main mining loop and background monitors."""
        self.display_banner()
        
        self.mining = True
        self.miner_core.mining_active = True
        self.stats_monitor.running = True
        
        # Start background monitors
        stats_thread = threading.Thread(target=self.stats_monitor.stats_monitor_thread, args=(self.session_manager,), daemon=True)
        stats_thread.start()
        
        performance_thread = threading.Thread(target=self.stats_monitor.monitor_system_performance, daemon=True)
        performance_thread.start()
        
        consecutive_failures = 0
        max_consecutive_failures = 5
        
        try:
            while self.mining and not self.shutdown_requested:
                if self.paused:
                    time.sleep(1)
                    continue
                
                try:
                    block_data = self.miner_core.generate_block_data(self.user_id)
                    self.logger.log('INFO', "Starting mining job...")
                    
                    result = self.miner_core.mine_block(block_data)
                    
                    if result and self.mining and not self.shutdown_requested:
                        system_info = {
                            'threads': self.config.threads,
                            'cpu_usage': self.stats.get('cpu_usage', 0),
                            'memory_usage': self.stats.get('memory_usage', 0)
                        }
                        submit_result = self.api_handler.submit_block(
                            self.user_id, result['hash'], result['nonce'], self.config.difficulty,
                            int(self.stats.get('hash_rate', 0)), system_info
                        )
                        
                        if submit_result.get('success'):
                            consecutive_failures = 0
                            with self.stats_lock:
                                self.stats['accepted_blocks'] += 1
                                self.stats['blocks_mined'] += 1
                                self.stats['last_block_time'] = time.time()
                                self.stats['total_earnings'] += float(submit_result['data'].get('final_reward', 0))
                                self.stats['current_balance'] = float(submit_result['data'].get('new_balance', 0))
                                self.stats['power_level'] = submit_result['data'].get('power_level', 'low')
                                if self.stats['accepted_blocks'] > 1:
                                    elapsed = time.time() - self.stats['start_time']
                                    self.stats['average_block_time'] = elapsed / self.stats['accepted_blocks']
                            
                            # Enhanced logging for accepted block
                            reward = submit_result['data'].get('final_reward', 0)
                            balance = submit_result['data'].get('new_balance', 0)
                            block_num = submit_result['data'].get('block_number', 0)
                            power_level = submit_result['data'].get('power_level', 'unknown')
                            
                            success_rate = (self.stats['accepted_blocks'] / 
                                            (self.stats['accepted_blocks'] + self.stats['rejected_blocks']) * 100) if (self.stats['accepted_blocks'] + self.stats['rejected_blocks']) > 0 else 100
                            
                            self.logger.log('SUCCESS', 
                                            f"Accepted {self.stats['accepted_blocks']}/{self.stats['accepted_blocks'] + self.stats['rejected_blocks']} "
                                            f"({success_rate:.1f}%) ∙ +{reward} PHN ∙ Balance: {balance} PHN ∙ "
                                            f"Block #{block_num} ∙ Power: {power_level.upper()}")
                            
                            self.session_manager.save_session_cache(self.user_id, self.username, self.stats)
                            time.sleep(1) # Brief pause before next block
                        else:
                            with self.stats_lock:
                                self.stats['rejected_blocks'] += 1
                                if submit_result.get('retryable', True): # Increment network errors only if retryable
                                    self.stats['network_errors'] += 1
                            consecutive_failures += 1
                            self.logger.log('WARNING', f"Block submission failed ({consecutive_failures}/{max_consecutive_failures}): {submit_result.get('error', 'Unknown')}")
                            time.sleep(2)
                    else:
                        if not self.shutdown_requested and not self.paused:
                            self.logger.log('INFO', "No solution found, generating new job...")
                            time.sleep(1)
                        
                    if consecutive_failures >= max_consecutive_failures:
                        self.logger.log('ERROR', "Too many consecutive failures, pausing for 30 seconds...")
                        time.sleep(30)
                        consecutive_failures = 0
                        
                except Exception as e:
                    self.logger.log('ERROR', f"Mining loop error: {e}")
                    time.sleep(5)
                    
        except KeyboardInterrupt:
            self.logger.log('WARNING', "Mining stopped by user (Ctrl+C)")
            self.shutdown_requested = True
            
        except Exception as e:
            self.logger.log('ERROR', f"Mining error: {e}")
            
        finally:
            self.mining = False
            self.miner_core.mining_active = False
            self.stats_monitor.running = False
            self.logger.log('INFO', "Stopping mining threads and monitors...")
            time.sleep(2) # Give threads a moment to shut down
            
            self.stats_monitor.print_stats()
            self.session_manager.save_session_cache(self.user_id, self.username, self.stats)
            self.logger.log('SUCCESS', "Mining session ended. Thank you for mining Phonesium!")

def main():
    """Main entry point for the Phonesium Mining Client."""
    parser = argparse.ArgumentParser(
        description='Phonesium Mining Client v2.0 - Enhanced Edition',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
python app.py                          # Interactive login
python app.py --threads 8              # Use 8 threads
python app.py --difficulty 6           # Set difficulty to 6
python app.py --user-id 123 --username miner1  # Skip login
python app.py --clear-cache            # Clear session cache
python app.py --url https://myserver.com  # Custom server
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
    
    app = PhonesiumMinerApp()
    
    # Apply command line arguments to config
    app.config.update_from_args(args)
    
    if args.clear_cache:
        app.session_manager.clear_session_cache()
        print("Session cache cleared!")
        return
    
    # Handle direct user ID login
    if args.user_id:
        app.user_id = args.user_id
        app.username = args.username or f"user_{args.user_id}"
        with app.stats_lock:
            app.stats['user_id'] = app.user_id
            app.stats['username'] = app.username
        app.logger.log('INFO', f"Using User ID: {args.user_id}")
    else:
        # Interactive login
        if not app.interactive_login():
            app.logger.log('ERROR', "Authentication failed")
            sys.exit(1)
    
    # Start mining
    try:
        app.start_mining()
    except Exception as e:
        app.logger.log('ERROR', f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
