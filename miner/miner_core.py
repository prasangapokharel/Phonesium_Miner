import hashlib
import time
import random
import threading
import os
import psutil # Import psutil for PID checking
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Dict, Any
from .logger import Logger
from .config import MinerConfig

class MinerCore:
    """Encapsulates the core hashing and mining logic."""
    
    # Define a PID file path. It will be created in the current working directory.
    PID_FILE = 'phonesium_miner.pid'

    def __init__(self, config: MinerConfig, logger: Logger, stats_lock: threading.Lock, stats: Dict[str, Any]):
        self.config = config
        self.logger = logger
        self.stats_lock = stats_lock
        self.stats = stats # Shared stats dictionary
        self.mining_active = False # Controlled by the main app
        self.shutdown_requested = False # Controlled by the main app
        self.paused = False # Controlled by the main app
        self.last_hash_rates = [] # For auto-difficulty
        
        # Single instance enforcement
        self._is_locked = False
        self._acquire_single_instance_lock()

    def _acquire_single_instance_lock(self):
        """
        Attempts to acquire a lock to ensure only one instance of the miner is running.
        Uses a PID file. Raises RuntimeError if another instance is detected or lock fails.
        """
        if os.path.exists(self.PID_FILE):
            try:
                with open(self.PID_FILE, 'r') as f:
                    pid = int(f.read().strip())
                
                if psutil.pid_exists(pid):
                    self.logger.log('ERROR', f"Another instance of the miner is already running with PID {pid}.")
                    self.logger.log('ERROR', "Please close the existing miner or delete the lock file if it's a stale lock.")
                    raise RuntimeError("Another miner instance is already running.")
                else:
                    self.logger.log('WARNING', f"Stale PID file found ({self.PID_FILE}). Cleaning up and proceeding.")
                    os.remove(self.PID_FILE)
            except (ValueError, FileNotFoundError, OSError) as e:
                self.logger.log('WARNING', f"Error reading or cleaning up PID file: {e}. Attempting to proceed.")
                if os.path.exists(self.PID_FILE):
                    try:
                        os.remove(self.PID_FILE)
                    except OSError:
                        self.logger.log('ERROR', f"Could not remove stale PID file {self.PID_FILE}. Please remove it manually.")
                        raise RuntimeError("Could not remove stale PID file.")
        
        try:
            with open(self.PID_FILE, 'w') as f:
                f.write(str(os.getpid()))
            self._is_locked = True
            self.logger.log('INFO', f"Acquired single instance lock with PID {os.getpid()}")
        except IOError as e:
            self.logger.log('ERROR', f"Failed to create PID file {self.PID_FILE}: {e}")
            raise RuntimeError("Failed to acquire single instance lock.")

    def release_single_instance_lock(self):
        """Releases the single instance lock by deleting the PID file."""
        if self._is_locked and os.path.exists(self.PID_FILE):
            try:
                os.remove(self.PID_FILE)
                self.logger.log('INFO', "Released single instance lock.")
                self._is_locked = False
            except OSError as e:
                self.logger.log('ERROR', f"Failed to remove PID file {self.PID_FILE}: {e}")

    def calculate_hash(self, data: str, nonce: int) -> str:
        """Calculates the hash for given data and nonce using configured algorithm."""
        message = f"{data}{nonce}".encode('utf-8')
        hash_algorithm = os.getenv('HASH_ALGORITHM', 'sha256').lower()
        
        if hash_algorithm == 'sha256':
            return hashlib.sha256(message).hexdigest()
        elif hash_algorithm == 'sha1':
            return hashlib.sha1(message).hexdigest()
        elif hash_algorithm == 'md5':
            return hashlib.md5(message).hexdigest()
        else:
            return hashlib.sha256(message).hexdigest() # Default fallback

    def is_valid_hash(self, hash_value: str, difficulty: int) -> bool:
        """Checks if a hash meets the current difficulty requirement."""
        if not hash_value or len(hash_value) < difficulty:
            return False
        return hash_value.startswith('0' * difficulty)

    def adjust_difficulty(self):
        """Auto-adjusts difficulty based on recent hash rates."""
        if not self.config.auto_difficulty:
            return
        
        with self.stats_lock:
            if len(self.last_hash_rates) >= 5:
                avg_rate = sum(self.last_hash_rates) / len(self.last_hash_rates)
                
                if avg_rate > 1000000 and self.config.difficulty < 8:
                    self.config.difficulty += 1
                    self.logger.log('INFO', f"Difficulty increased to {self.config.difficulty}")
                elif avg_rate < 100000 and self.config.difficulty > 3:
                    self.config.difficulty -= 1
                    self.logger.log('INFO', f"Difficulty decreased to {self.config.difficulty}")

    def generate_block_data(self, user_id: int) -> str:
        """Generates unique block data for mining."""
        timestamp = int(time.time())
        random_data = random.randint(1000000, 9999999)
        # Use a stable session ID based on miner start time for consistency
        session_id = hash(str(self.stats['start_time'])) % 1000000
        return f"phonesium_{timestamp}_{random_data}_{user_id}_{session_id}"

    def mine_block_thread(self, block_data: str, start_nonce: int, nonce_range: int, thread_id: int) -> Optional[Dict[str, Any]]:
        """Individual mining thread function."""
        nonce = start_nonce
        end_nonce = start_nonce + nonce_range
        hashes_computed = 0
        thread_start_time = time.time()
        
        try:
            while self.mining_active and nonce < end_nonce and not self.shutdown_requested and not self.paused:
                batch_end = min(nonce + self.config.hash_batch_size, end_nonce)
                
                for batch_nonce in range(nonce, batch_end):
                    if not self.mining_active or self.shutdown_requested or self.paused:
                        return None
                    
                    block_hash = self.calculate_hash(block_data, batch_nonce)
                    hashes_computed += 1
                    
                    with self.stats_lock:
                        self.stats['total_hashes'] += 1
                    
                    if self.is_valid_hash(block_hash, self.config.difficulty):
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
                
                if self.config.cpu_limit < 100:
                    time.sleep(0.001 * (100 - self.config.cpu_limit) / 100)
            
            return None
        except Exception as e:
            self.logger.log('ERROR', f"Mining thread {thread_id} error: {e}")
            return None

    def mine_block(self, block_data: str) -> Optional[Dict[str, Any]]:
        """Manages multi-threaded block mining."""
        # Check lock status before starting a new mining block
        if not self._is_locked:
            self.logger.log('ERROR', "MinerCore lock not acquired. Cannot start mining.")
            return None

        self.logger.log('INFO', f"Mining with {self.config.threads} threads (Difficulty: {self.config.difficulty})")
        
        start_time = time.time()
        solution_found = False
        
        with ThreadPoolExecutor(max_workers=self.config.threads) as executor:
            futures = []
            for i in range(self.config.threads):
                start_nonce = i * self.config.nonce_range + random.randint(0, 100000)
                future = executor.submit(
                    self.mine_block_thread,
                    block_data,
                    start_nonce,
                    self.config.nonce_range,
                    i
                )
                futures.append(future)
            
            try:
                for future in as_completed(futures, timeout=self.config.mining_timeout):
                    if not self.mining_active or self.shutdown_requested:
                        break
                    
                    result = future.result()
                    if result and not solution_found:
                        solution_found = True
                        for f in futures: # Cancel remaining futures
                            if not f.done():
                                f.cancel()
                        
                        mining_time = time.time() - start_time
                        hash_rate = result['nonce'] / mining_time if mining_time > 0 else 0
                        
                        with self.stats_lock:
                            self.stats['hash_rate'] = hash_rate
                            self.stats['best_hash_rate'] = max(self.stats['best_hash_rate'], hash_rate)
                            self.last_hash_rates.append(hash_rate)
                            if len(self.last_hash_rates) > 10:
                                self.last_hash_rates.pop(0)
                        
                        self.logger.log('SUCCESS', f"Block found! Hash: {result['hash'][:16]}...")
                        self.logger.log('SUCCESS', f"Nonce: {result['nonce']:,} | Time: {mining_time:.2f}s | Rate: {hash_rate:.0f} H/s")
                        
                        self.adjust_difficulty()
                        return result
                
                if not solution_found and self.mining_active and not self.shutdown_requested:
                    self.logger.log('INFO', f"No solution found in {self.config.mining_timeout}s, generating new job...")
            except Exception as e:
                self.logger.log('ERROR', f"Mining execution error: {e}")
            finally:
                for f in futures:
                    if not f.done():
                        f.cancel()
            return None
