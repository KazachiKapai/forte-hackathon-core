from typing import Any, Optional

from ...logging_config import configure_logging

_LOGGER = configure_logging()

try:
	from langchain_core.language_models.chat_models import BaseChatModel  # type: ignore
	from langchain_core.messages import AIMessage, BaseMessage, HumanMessage  # type: ignore
except Exception:  # pragma: no cover
	BaseChatModel = Any  # type: ignore
	AIMessage = Any  # type: ignore
	BaseMessage = Any  # type: ignore
	HumanMessage = Any  # type: ignore

try:
	from langchain_openai import ChatOpenAI  # type: ignore
except Exception:  # pragma: no cover
	ChatOpenAI = None  # type: ignore

try:
	from langchain_google_genai import ChatGoogleGenerativeAI  # type: ignore
except Exception:  # pragma: no cover
	ChatGoogleGenerativeAI = None  # type: ignore


class LLMFactory:
	def __init__(
		self,
		provider: str,
		model: str,
		openai_api_key: Optional[str],
		google_api_key: Optional[str],
		timeout: float,
	) -> None:
		self.provider = (provider or "").strip().lower() or "openai"
		self.model = model
		self.openai_api_key = openai_api_key
		self.google_api_key = google_api_key
		self.timeout = timeout

	def build(self) -> Optional[BaseChatModel]:
		if self.provider == "openai":
			if ChatOpenAI is None:
				raise RuntimeError("langchain-openai is not installed")
			if not self.openai_api_key:
				raise RuntimeError("OPENAI_API_KEY is required for agentic mode")
			return ChatOpenAI(model=self.model, api_key=self.openai_api_key, temperature=0, timeout=self.timeout)
		if self.provider in {"google", "gemini"}:
			if ChatGoogleGenerativeAI is None:
				raise RuntimeError("langchain-google-genai is not installed")
			if not self.google_api_key:
				raise RuntimeError("GOOGLE_API_KEY is required for Google provider")
			return ChatGoogleGenerativeAI(model=self.model, api_key=self.google_api_key, temperature=0)
		raise RuntimeError(f"Unsupported agentic provider: {self.provider}")


class LLMClient:
	def __init__(self, model: Optional[BaseChatModel], unavailable_reason: Optional[str] = None) -> None:
		self.model = model
		self.unavailable_reason = unavailable_reason

	@property
	def available(self) -> bool:
		return self.model is not None

	def generate(self, prompt: str) -> str:
		if not self.model:
			raise RuntimeError(self.unavailable_reason or "LLM backend is not configured")
		message = HumanMessage(content=prompt)
		response = self.model.invoke([message])
		return self._extract_text(response)

	def _extract_text(self, response: Any) -> str:
		if isinstance(response, str):
			return response
		if isinstance(response, AIMessage):
			content = response.content
			if isinstance(content, str):
				return content
			if isinstance(content, list):
				parts = []
				for chunk in content:
					if isinstance(chunk, dict):
						text = chunk.get("text")
						if text:
							parts.append(text)
				return "\n".join(parts)
		if isinstance(response, BaseMessage):
			if isinstance(response.content, str):
				return response.content
		text = getattr(response, "text", None)
		if isinstance(text, str):
			return text
		return str(response)


def build_llm_client(provider: str, model: str, openai_api_key: Optional[str], google_api_key: Optional[str], timeout: float) -> LLMClient:
	try:
		backend = LLMFactory(provider, model, openai_api_key, google_api_key, timeout).build()
		return LLMClient(backend)
	except Exception as exc:
		_LOGGER.warning("Agentic LLM disabled", extra={"error": str(exc)})
		return LLMClient(model=None, unavailable_reason=str(exc))



