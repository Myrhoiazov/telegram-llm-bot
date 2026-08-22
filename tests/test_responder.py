from app.application.responder import SYSTEM_PROMPT, LLMResponder


class FakeGenerator:
    def __init__(self, reply: str) -> None:
        self._reply = reply
        self.last_call = None

    def generate(self, prompt: str, system: str | None = None) -> str:
        self.last_call = {"prompt": prompt, "system": system}
        return self._reply


def test_llm_responder_passes_system_prompt_to_generator():
    generator = FakeGenerator("answer")
    responder = LLMResponder(generator)

    result = responder.respond("question")

    assert result == "answer"
    assert generator.last_call == {"prompt": "question", "system": SYSTEM_PROMPT}
