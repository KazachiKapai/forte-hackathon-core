from typing import Any
from app.review.agentic.llm import LLMClient


class FakeModel:
	def __init__(self, resp: Any) -> None:
		self._resp = resp

	def invoke(self, messages):
		# messages should be a list containing a HumanMessage; we ignore here
		return self._resp


def test_llm_client_generate_raises_when_unavailable():
	client = LLMClient(model=None, unavailable_reason="x")
	try:
		client.generate("hi")
		assert False, "should raise"
	except RuntimeError as e:
		assert "x" in str(e)


def test_llm_client_generate_returns_plain_string():
	client = LLMClient(model=FakeModel("answer"))
	assert client.available is True
	out = client.generate("hi")
	assert out == "answer"


def test_llm_client_extracts_text_attr():
	class Resp:
		def __init__(self) -> None:
			self.text = "T"
	client = LLMClient(model=FakeModel(Resp()))
	out = client.generate("hi")
	assert out == "T"


