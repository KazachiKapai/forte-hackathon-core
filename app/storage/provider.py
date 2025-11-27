import os
from typing import Optional
from .base import KeyValueStore
from .kv_store import FileKeyValueStore, MongoKeyValueStore
from ..config.logging_config import configure_logging

_LOGGER = configure_logging()
_store: Optional[KeyValueStore] = None


def get_kv_store() -> KeyValueStore:
	global _store
	if _store is not None:
		return _store
	# Prefer Mongo when configured
	mongo_url = os.environ.get("MONGO_URL")
	if not mongo_url:
		host = os.environ.get("MONGO_HOST")
		port = os.environ.get("MONGO_PORT", "27017")
		user = os.environ.get("MONGO_USERNAME") or os.environ.get("MONGO_INITDB_ROOT_USERNAME")
		pw = os.environ.get("MONGO_PASSWORD") or os.environ.get("MONGO_INITDB_ROOT_PASSWORD")
		auth_db = os.environ.get("MONGO_AUTH_SOURCE", "admin")
		if host and user and pw:
			mongo_url = f"mongodb://{user}:{pw}@{host}:{port}/?authSource={auth_db}"
	if mongo_url:
		db_name = os.environ.get("MONGO_DB", "app")
		try:
			_store = MongoKeyValueStore(mongo_url, database=db_name)
			_LOGGER.info("Using MongoKeyValueStore", extra={"db": db_name})
			return _store
		except Exception as e:
			_LOGGER.warning("Failed to initialize MongoKeyValueStore, falling back", extra={"error": str(e)})
	# fallback
	_store = FileKeyValueStore()
	_LOGGER.info("Using FileKeyValueStore")
	return _store


