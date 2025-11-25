import json
import os
from typing import Any, Dict
from ..config.logging_config import configure_logging

_LOGGER = configure_logging()

_DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.getcwd(), "data"))


def ensure_data_dir() -> None:
	try:
		os.makedirs(_DATA_DIR, exist_ok=True)
	except Exception:
		pass


def file_path(name: str) -> str:
	ensure_data_dir()
	return os.path.join(_DATA_DIR, name)


def load_json(name: str, default: Any) -> Any:
	path = file_path(name)
	try:
		with open(path, "r", encoding="utf-8") as f:
			return json.load(f)
	except Exception:
		return default


def save_json(name: str, data: Any) -> None:
	path = file_path(name)
	tmp = f"{path}.tmp"
	with open(tmp, "w", encoding="utf-8") as f:
		json.dump(data, f, ensure_ascii=False, indent=2)
	os.replace(tmp, path)


