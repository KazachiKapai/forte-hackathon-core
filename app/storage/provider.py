import os
from typing import Optional
from .base import KeyValueStore
from .kv_store import FileKeyValueStore, PostgresKeyValueStore
from ..config.logging_config import configure_logging

_LOGGER = configure_logging()
_store: Optional[KeyValueStore] = None


def get_kv_store() -> KeyValueStore:
	global _store
	if _store is not None:
		return _store
	db_url = os.environ.get("DATABASE_URL")
	if db_url:
		try:
			_store = PostgresKeyValueStore(db_url)
			_LOGGER.info("Using PostgresKeyValueStore")
			return _store
		except Exception as e:
			_LOGGER.warning("Failed to initialize PostgresKeyValueStore, falling back to FileKeyValueStore", extra={"error": str(e)})
	# fallback
	_store = FileKeyValueStore()
	_LOGGER.info("Using FileKeyValueStore")
	return _store


