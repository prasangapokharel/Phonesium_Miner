import time
import threading
import psutil
from datetime import datetime
from typing import Dict, Any
from .logger import Logger # Adjusted import
from .config import MinerConfig # Adjusted import
from .session_manager import SessionManager # Adjusted import

class StatsMonitor:
    """Monitors system performance and displays mining statistics."""
    def __init__(self, config: MinerConfig, logger: Logger, stats_lock: threading.Lock, stats: Dict[str, Any]):
        self.config = config
        self.logger = logger
        self.stats_lock = stats_lock
        self.stats = stats # Shared stats dictionary
        self.running = False # Controlled by the main app

    def monitor_system_performance(self):
        """Background thread to monitor CPU and memory usage."""
        while self.running:
            try:
                cpu_percent = psutil.cpu_percent(interval=1)
                memory = psutil.virtual_memory()
                memory_percent = memory.percent
                
                with self.stats_lock:
                    self.stats['cpu_usage'] = cpu_percent
                    self.stats['memory_usage'] = memory_percent
                    self.stats['session_uptime'] = time.time() - self.stats['start_time']
                    
                if cpu_percent > self.config.cpu_limit:
                    self.logger.log('WARNING', f"High CPU usage ({cpu_percent:.1f}%), throttling...")
                    time.sleep(1)
                    
                if memory_percent > 90:
                    self.logger.log('WARNING', f"High memory usage ({memory_percent:.1f}%)")
                    
                time.sleep(5) # Check every 5 seconds
                
            except Exception as e:
                self.logger.log('DEBUG', f"Performance monitoring error: {e}")
                time.sleep(10)

    def print_stats(self):
        """Prints comprehensive mining statistics to the console."""
        with self.stats_lock:
            elapsed = time.time() - self.stats['start_time']
            avg_hash_rate = self.stats['total_hashes'] / elapsed if elapsed > 0 else 0
            total_attempts = self.stats['accepted_blocks'] + self.stats['rejected_blocks']
            success_rate = (total_attempts > 0) and (self.stats['accepted_blocks'] / total_attempts * 100) or 0
            
            print(f"\n{'='*70}")
            print(f"📊 PHONESIUM MINING STATISTICS - ENHANCED")
            print(f"{'='*70}")
            print(f"👤 Miner: {self.stats['username']} (ID: {self.stats['user_id']})")
            print(f"⏱️  Runtime: {elapsed:.0f}s ({elapsed/3600:.1f}h)")
            print(f"🧵 Threads: {self.config.threads} | CPU: {self.stats['cpu_usage']:.1f}% | RAM: {self.stats['memory_usage']:.1f}%")
            print(f"💎 Difficulty: {self.config.difficulty} leading zeros")
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
            
            if elapsed > 0:
                blocks_per_hour = (self.stats['accepted_blocks'] / elapsed) * 3600
                earnings_per_hour = (self.stats['total_earnings'] / elapsed) * 3600
                print(f"📊 Blocks/Hour: {blocks_per_hour:.2f}")
                print(f"💵 PHN/Hour: {earnings_per_hour:.6f}")
            
            print(f"{'='*70}\n")

    def stats_monitor_thread(self, session_manager: SessionManager):
        """Background thread to periodically print stats and auto-save session."""
        while self.running:
            time.sleep(60) # Every minute
            if self.running:
                self.print_stats()
                
                with self.stats_lock:
                    # Auto-save session periodically
                    if self.stats['accepted_blocks'] % 10 == 0 and self.stats['accepted_blocks'] > 0:
                        session_manager.save_session_cache(
                            self.stats['user_id'], self.stats['username'], self.stats
                        )
