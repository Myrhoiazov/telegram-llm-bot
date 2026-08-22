import time

from app.telegram.client import TelegramAPIError
from app.telegram.typing_indicator import TypingIndicator


class FakeTelegramClient:
    def __init__(self, fail_times: int = 0) -> None:
        self.calls: list[tuple[int, str]] = []
        self._fail_times = fail_times

    def send_chat_action(self, chat_id: int, action: str = "typing") -> None:
        if self._fail_times > 0:
            self._fail_times -= 1
            raise TelegramAPIError("boom")
        self.calls.append((chat_id, action))


def test_typing_indicator_sends_action_repeatedly_until_stopped():
    client = FakeTelegramClient()

    with TypingIndicator(client, chat_id=123, interval_seconds=0.01):
        time.sleep(0.05)

    assert len(client.calls) >= 2
    assert all(call == (123, "typing") for call in client.calls)


def test_typing_indicator_stops_sending_after_context_exit():
    client = FakeTelegramClient()

    with TypingIndicator(client, chat_id=123, interval_seconds=0.01):
        time.sleep(0.03)

    count_after_exit = len(client.calls)
    time.sleep(0.05)

    assert len(client.calls) == count_after_exit


def test_typing_indicator_survives_telegram_api_errors():
    client = FakeTelegramClient(fail_times=2)

    with TypingIndicator(client, chat_id=123, interval_seconds=0.01):
        time.sleep(0.08)

    assert len(client.calls) >= 1
