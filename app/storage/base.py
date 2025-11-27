from typing import Any, Protocol


class KeyValueStore(Protocol):
	def get_json(self, name: str, default: Any) -> Any: ...
	def set_json(self, name: str, data: Any) -> None: ...


