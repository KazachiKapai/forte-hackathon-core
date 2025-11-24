import os
import threading
import time
from typing import Dict, Optional


class _CooldownStore:
	def __init__(self, ttl_seconds: int = 20, capacity: int = 8192) -> None:
		self._ttl = max(1, ttl_seconds)
		self._capacity = max(256, capacity)
		self._lock = threading.Lock()
		self._data: Dict[str, float] = {}

	def acquire(self, key: str) -> bool:
		"""
		Returns True on first acquisition (not in cooldown), and starts cooldown.
		Returns False if still cooling down.
		"""
		now = time.time()
		with self._lock:
			if len(self._data) > self._capacity:
				self._cleanup_locked(now)
			exp = self._data.get(key)
			if exp and exp > now:
				return False
			self._data[key] = now + self._ttl
			return True

	def _cleanup_locked(self, now: float) -> None:
		for k, exp in list(self._data.items()):
			if exp <= now:
				self._data.pop(k, None)


_singleton: Optional[_CooldownStore] = None
_lock = threading.Lock()


def get_cooldown_store() -> _CooldownStore:
	global _singleton
	if _singleton is None:
		with _lock:
			if _singleton is None:
				try:
					ttl = int(os.environ.get("MR_COOLDOWN_SECONDS", "20") or "20")
				except Exception:
					ttl = 20
				_singleton = _CooldownStore(ttl_seconds=ttl, capacity=8192)
	return _singleton  # type: ignore[return-value]


