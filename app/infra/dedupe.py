import os
import threading
import time
from typing import Dict, Tuple, Optional


class _DedupeStore:
	def __init__(self, ttl_seconds: int = 300, capacity: int = 4096) -> None:
		self._ttl = max(1, ttl_seconds)
		self._capacity = max(128, capacity)
		self._lock = threading.Lock()
		self._data: Dict[str, float] = {}

	def should_process(self, key: str) -> bool:
		"""
		Returns True if this key has not been seen recently (within TTL),
		and records it. Returns False if it was recently seen (duplicate).
		"""
		now = time.time()
		with self._lock:
			# cleanup opportunistically
			if len(self._data) > self._capacity:
				self._cleanup_locked(now)
			exp = self._data.get(key)
			if exp and exp > now:
				return False
			# record/refresh
			self._data[key] = now + self._ttl
			return True

	def _cleanup_locked(self, now: float) -> None:
		# remove expired entries; if still big, trim oldest by bumping ttl window
		remove_keys = [k for k, exp in self._data.items() if exp <= now]
		for k in remove_keys:
			self._data.pop(k, None)
		# if still above capacity, drop arbitrary extras
		if len(self._data) > self._capacity:
			for k in list(self._data.keys())[: len(self._data) - self._capacity]:
				self._data.pop(k, None)


_singleton: Optional[_DedupeStore] = None
_lock = threading.Lock()


def get_dedupe_store() -> _DedupeStore:
	global _singleton
	if _singleton is None:
		with _lock:
			if _singleton is None:
				try:
					ttl = int(os.environ.get("DEDUPE_TTL_SECONDS", "300") or "300")
				except Exception:
					ttl = 300
				_singleton = _DedupeStore(ttl_seconds=ttl, capacity=4096)
	return _singleton  # type: ignore[return-value]


def init_dedupe_store(ttl_seconds: int) -> None:
	"""
	Initialize or re-initialize the dedupe store with an explicit TTL.
	"""
	global _singleton
	with _lock:
		_singleton = _DedupeStore(ttl_seconds=ttl_seconds, capacity=4096)


