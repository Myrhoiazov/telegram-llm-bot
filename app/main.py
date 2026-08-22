"""Entry point: builds dependencies and runs the Telegram polling loop."""
from __future__ import annotations

import logging

from app.application.bot_service import BotService
from app.application.responder import LLMResponder
from app.config import Config, ConfigError, load_config
from app.inference.ollama import OllamaProvider
from app.telegram.client import TelegramAPIError, TelegramClient
from app.telegram.typing_indicator import TypingIndicator
from app.telegram.updates import parse_updates

logger = logging.getLogger(__name__)

ACCESS_DENIED_REPLY = "Доступ ограничен."


def main() -> None:
    try:
        config = load_config()
    except ConfigError as exc:
        logging.basicConfig(level="INFO")
        logger.error("Configuration error: %s", exc)
        raise SystemExit(1) from exc

    logging.basicConfig(level=config.log_level)

    telegram_client = TelegramClient(
        token=config.telegram_bot_token,
        poll_timeout_seconds=config.poll_timeout_seconds,
        request_timeout_seconds=config.request_timeout_seconds,
    )
    ollama_provider = OllamaProvider(
        base_url=config.ollama_base_url,
        model=config.ollama_model,
        timeout_seconds=config.request_timeout_seconds,
    )
    bot_service = BotService(LLMResponder(ollama_provider))

    try:
        run_polling_loop(telegram_client, bot_service, config)
    except KeyboardInterrupt:
        logger.info("Shutting down")


def run_polling_loop(telegram_client: TelegramClient, bot_service: BotService, config: Config) -> None:
    offset: int | None = None
    logger.info("Starting polling loop")
    while True:
        try:
            payload = telegram_client.get_updates(offset)
        except TelegramAPIError:
            logger.exception("Failed to fetch updates, retrying")
            continue

        raw_updates = payload.get("result", [])

        for message in parse_updates(payload):
            if config.allowed_chat_id is not None and message.chat_id != config.allowed_chat_id:
                logger.warning("Ignoring message from disallowed chat_id=%s", message.chat_id)
                try:
                    telegram_client.send_message(message.chat_id, ACCESS_DENIED_REPLY)
                except TelegramAPIError:
                    logger.exception("Failed to send access-denied reply to chat %s", message.chat_id)
                continue

            with TypingIndicator(telegram_client, message.chat_id, config.typing_action_interval_seconds):
                reply = bot_service.handle_message(message.text)
            try:
                telegram_client.send_message(message.chat_id, reply)
            except TelegramAPIError:
                logger.exception("Failed to send reply to chat %s", message.chat_id)

        if raw_updates:
            last_update_id = raw_updates[-1].get("update_id")
            if isinstance(last_update_id, int):
                offset = last_update_id + 1


if __name__ == "__main__":
    main()
