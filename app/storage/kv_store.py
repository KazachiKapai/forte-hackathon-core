import json
import os
from typing import Any
from pathlib import Path
from .base import KeyValueStore
from ..config.logging_config import configure_logging

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
			with open(path, "r", encoding="utf-8") as f:
				return json.load(f)
		except Exception:
			return default
	
	def set_json(self, name: str, data: Any) -> None:
		path = self._file_path(name)
		tmp = f"{path}.tmp"
		with open(tmp, "w", encoding="utf-8") as f:
			json.dump(data, f, ensure_ascii=False, indent=2)
		os.replace(tmp, path)


class PostgresKeyValueStore(KeyValueStore):
	def __init__(self, database_url: str) -> None:
		self.database_url = database_url
		try:
			import psycopg  # type: ignore
			self._psycopg = psycopg
		except Exception as e:
			raise RuntimeError("psycopg is required for PostgresKeyValueStore") from e
		self._ensure_table()
	
	def _ensure_table(self) -> None:
		try:
			with self._psycopg.connect(self.database_url, autocommit=True) as conn:  # type: ignore[attr-defined]
				with conn.cursor() as cur:
					cur.execute(
						"""
						CREATE TABLE IF NOT EXISTS kv_store (
							name TEXT PRIMARY KEY,
							data JSONB NOT NULL
						)
						"""
					)
		except Exception:
			_LOGGER.exception("Failed to create kv_store table")
			raise
	
	def get_json(self, name: str, default: Any) -> Any:
		try:
			with self._psycopg.connect(self.database_url, autocommit=True) as conn:  # type: ignore[attr-defined]
				with conn.cursor() as cur:
					cur.execute("SELECT data FROM kv_store WHERE name = %s", (name,))
					row = cur.fetchone()
					if not row:
						return default
					return row[0]
		except Exception:
			_LOGGER.exception("kv_store get_json failed")
			return default
	
	def set_json(self, name: str, data: Any) -> None:
		try:
			with self._psycopg.connect(self.database_url, autocommit=True) as conn:  # type: ignore[attr-defined]
				with conn.cursor() as cur:
					cur.execute(
						"""
						INSERT INTO kv_store (name, data)
						VALUES (%s, %s)
						ON CONFLICT (name) DO UPDATE SET data = EXCLUDED.data
						""",
						(name, json.loads(json.dumps(data))),
					)
		except Exception:
			_LOGGER.exception("kv_store set_json failed")
			raise


