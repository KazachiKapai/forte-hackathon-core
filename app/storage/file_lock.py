import fcntl
import os
import time


class FileLock:
    def __init__(self, lock_file_path: str, timeout: int = 10, delay: float = 0.1):
        self.is_locked = False
        self.lock_file_path = lock_file_path
        self._lock_file = None
        self.timeout = timeout
        self.delay = delay

    def __enter__(self):
        start_time = time.time()
        while True:
            try:
                self._lock_file = open(self.lock_file_path, "w")
                fcntl.flock(self._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.is_locked = True
                return self
            except (IOError, BlockingIOError):
                if time.time() - start_time >= self.timeout:
                    raise TimeoutError(f"Timeout occurred while waiting for lock on {self.lock_file_path}")
                time.sleep(self.delay)

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.is_locked and self._lock_file:
            fcntl.flock(self._lock_file, fcntl.LOCK_UN)
            self._lock_file.close()
            self.is_locked = False
            try:
                os.remove(self.lock_file_path)
            except OSError:
                pass