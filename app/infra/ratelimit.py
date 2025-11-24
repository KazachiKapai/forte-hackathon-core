import os
import threading
import time
from typing import Dict


class _TokenBucket:
	def __init__(self, rate_per_sec: float, burst: int) -> None:
		self.rate = max(0.1, rate_per_sec)
		self.capacity = max(1, burst)
		self.tokens = self.capacity
		self.timestamp = time.time()

	def allow(self) -> bool:
		now = time.time()
		elapsed = now - self.timestamp
		self.timestamp = now
		self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
		if self.tokens >= 1.0:
			self.tokens -= 1.0
			return True
		return False


class RateLimiter:
	def __init__(self, per_minute: int, burst: int) -> None:
		rate_per_sec = max(1, per_minute) / 60.0
		self._rate_per_sec = rate_per_sec
		self._burst = max(1, burst)
		self._buckets: Dict[str, _TokenBucket] = {}
		self._lock = threading.Lock()

	def allow(self, key: str) -> bool:
		with self._lock:
			b = self._buckets.get(key)
			if b is None:
				b = _TokenBucket(self._rate_per_sec, self._burst)
				self._buckets[key] = b
			return b.allow()


_singleton: RateLimiter | None = None
_lock = threading.Lock()


def get_rate_limiter() -> RateLimiter:
	global _singleton
	if _singleton is None:
		with _lock:
			if _singleton is None:
				try:
					per_min = int(os.environ.get("RATE_LIMIT_PER_MIN", "60") or "60")
				except Exception:
					per_min = 60
				try:
					burst = int(os.environ.get("RATE_LIMIT_BURST", str(per_min)) or str(per_min))
				except Exception:
					burst = per_min
				_singleton = RateLimiter(per_minute=per_min, burst=burst)
	return _singleton  # type: ignore[return-value]


