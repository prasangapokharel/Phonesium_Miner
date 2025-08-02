import os
import multiprocessing

class MinerConfig:
    """Manages all configuration settings for the Phonesium Miner."""
    def __init__(self):
        self.base_url = os.getenv('BASE_URL', 'http://192.168.1.77:8000/')
        self.api_url = f"{self.base_url}/api.php"
        self.difficulty = int(os.getenv('DIFFICULTY', 5))
        self.api_secret = os.getenv('API_SECRET', 'TTXRESS2')
        self.timeout = int(os.getenv('TIMEOUT', 30))
        self.retry_attempts = int(os.getenv('RETRY_ATTEMPTS', 5))
        self.retry_delay = int(os.getenv('RETRY_DELAY', 2))
        self.threads = min(int(os.getenv('THREADS', 4)), multiprocessing.cpu_count())
        self.nonce_range = int(os.getenv('NONCE_RANGE', 2000000))
        self.hash_batch_size = int(os.getenv('HASH_BATCH_SIZE', 50000))
        self.auto_difficulty = os.getenv('AUTO_DIFFICULTY', 'false').lower() == 'true'
        self.cpu_limit = int(os.getenv('CPU_LIMIT', 80))
        self.memory_limit = int(os.getenv('MEMORY_LIMIT', 1024))
        self.cache_file = 'phonesium_session.cache'
        self.mining_timeout = int(os.getenv('MINING_TIMEOUT', '120')) # 2 minutes default

    def update_from_args(self, args):
        """Updates configuration based on command-line arguments."""
        if args.url:
            self.base_url = args.url
            self.api_url = f"{args.url}/api.php"
        if args.threads:
            self.threads = min(args.threads, multiprocessing.cpu_count())
        if args.difficulty:
            self.difficulty = max(1, min(args.difficulty, 10))
        if args.auto_difficulty:
            self.auto_difficulty = True
        if args.cpu_limit:
            self.cpu_limit = max(10, min(args.cpu_limit, 100))
        if args.log_file:
            os.environ['LOG_TO_FILE'] = 'true'
