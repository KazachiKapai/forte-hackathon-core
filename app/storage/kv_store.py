import json
import os
from pathlib import Path
from typing import Any

from ..config.logging_config import configure_logging
from .base import KeyValueStore

_LOGGER = configure_logging()


class FileKeyValueStore(KeyValueStore):
	def __init__(self, data_dir: str | None = None) -> None:
		self.data_dir = data_dir or os.environ.get("DATA_DIR") or str(Path.cwd() / "data")
		Path(self.data_dir).mkdir(parents=True, exist_ok=True)
	
	def _file_path(self, name: str) -> str:
		return str(Path(self.data_dir) / name)
	
	def get_json(self, name: str, default: Any) -> Any:
		path = self._file_path(name)
		try:
			with open(path, encoding="utf-8") as f:
				return json.load(f)
		except Exception:
			return default
	
	def set_json(self, name: str, data: Any) -> None:
		path = self._file_path(name)
		tmp = f"{path}.tmp"
		with open(tmp, "w", encoding="utf-8") as f:
			json.dump(data, f, ensure_ascii=False, indent=2)
		os.replace(tmp, path)


class MongoKeyValueStore(KeyValueStore):
	def __init__(self, mongo_url: str, database: str = "app") -> None:
		try:
			from pymongo import MongoClient  # type: ignore
		except Exception as e:
			raise RuntimeError("pymongo is required for MongoKeyValueStore") from e
		self._MongoClient = MongoClient  # type: ignore[assignment]
		self.client = self._MongoClient(mongo_url, connect=True)
		self.db = self.client[database]
		self.col = self.db.get_collection("kv_store")
		# Ensure index on _id (name)
		try:
			self.col.create_index("_id", unique=True)
		except Exception:
			# Safe to ignore; default _id index exists
			pass
	
	def get_json(self, name: str, default: Any) -> Any:
		try:
			doc = self.col.find_one({"_id": name})
			if not doc:
				return default
			return doc.get("data", default)
		except Exception:
			_LOGGER.exception("kv_store get_json (mongo) failed")
			return default
	
	def set_json(self, name: str, data: Any) -> None:
		try:
			self.col.update_one({"_id": name}, {"$set": {"data": json.loads(json.dumps(data))}}, upsert=True)
		except Exception:
			_LOGGER.exception("kv_store set_json (mongo) failed")
			raise


