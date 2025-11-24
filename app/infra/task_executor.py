import os
import threading
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Any, Callable, Optional


class TaskExecutor:
	def __init__(self, max_workers: int) -> None:
		# Ensure at least 2 to avoid nested task starvation
		self._max_workers = max(2, max_workers)
		self._executor = ThreadPoolExecutor(max_workers=self._max_workers, thread_name_prefix="mr-worker")

	def submit(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Future:
		return self._executor.submit(fn, *args, **kwargs)

	def shutdown(self, wait: bool = True) -> None:
		self._executor.shutdown(wait=wait, cancel_futures=False)


_singleton_lock = threading.Lock()
_singleton_executor: Optional[TaskExecutor] = None


def get_shared_executor() -> TaskExecutor:
	global _singleton_executor
	if _singleton_executor is None:
		with _singleton_lock:
			if _singleton_executor is None:
				try:
					raw = os.environ.get("WORKER_CONCURRENCY", "4")
					max_workers = int(raw or "4")
				except Exception:
					max_workers = 4
				_singleton_executor = TaskExecutor(max_workers=max_workers)
	return _singleton_executor  # type: ignore[return-value]


def init_shared_executor(max_workers: int) -> None:
	"""
	Initialize or re-initialize the shared executor with an explicit concurrency.
	"""
	global _singleton_executor
	with _singleton_lock:
		if _singleton_executor is not None:
			_singleton_executor.shutdown(wait=False)
		_singleton_executor = TaskExecutor(max_workers=max_workers)


