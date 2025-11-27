from typing import Any
from .provider import get_kv_store


def load_json(name: str, default: Any) -> Any:
	store = get_kv_store()
	return store.get_json(name, default)


def save_json(name: str, data: Any) -> None:
	store = get_kv_store()
	store.set_json(name, data)


