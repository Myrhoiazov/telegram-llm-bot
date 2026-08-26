from app.application.bot_service import BotService


class FakeAgent:
    def __init__(self, reply="ok"):
        self._reply = reply
        self.calls = []

    def handle_message(self, chat_id, text):
        self.calls.append((chat_id, text))
        return self._reply


def test_handle_message_delegates_to_agent_with_chat_id_and_text():
    agent = FakeAgent(reply="hello back")
    service = BotService(agent)

    result = service.handle_message(chat_id=555, text="hi")

    assert result == "hello back"
    assert agent.calls == [(555, "hi")]
