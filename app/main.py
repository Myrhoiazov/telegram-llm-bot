"""Entry point: builds dependencies and runs the Telegram polling loop."""
from __future__ import annotations

import logging

from app.agent.loop import AgentLoop
from app.agent.system_prompt import build_system_prompt
from app.application.bot_service import BotService
from app.config import Config, ConfigError, load_config
from app.inference.ollama_chat import OllamaChatClient
from app.memory.store import ConversationStore
from app.telegram.client import TelegramAPIError, TelegramClient
from app.telegram.typing_indicator import TypingIndicator
from app.telegram.updates import parse_updates
from app.tools.exec_tool import ExecTool, build_exec_env

logger = logging.getLogger(__name__)

ACCESS_DENIED_REPLY = "Доступ ограничен."
NEW_CHAT_REPLY = "Начат новый диалог. Предыдущая история сохранена, но больше не используется как контекст."
UNEXPECTED_ERROR_REPLY = "Произошла непредвиденная ошибка при обработке сообщения. Попробуйте ещё раз."
NEW_CHAT_COMMAND = "/new"


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
    chat_client = OllamaChatClient(
        base_url=config.ollama_base_url,
        model=config.ollama_model,
        timeout_seconds=config.request_timeout_seconds,
    )
    store = ConversationStore(config.memory_db_path)
    exec_tool = ExecTool(
        workspace_dir=config.exec_workspace_dir,
        timeout_seconds=config.exec_timeout_seconds,
        env=build_exec_env(config),
    )
    agent = AgentLoop(
        chat_client=chat_client,
        tool=exec_tool,
        store=store,
        max_steps=config.agent_max_steps,
        max_context_messages=config.max_context_messages,
        system_prompt=build_system_prompt(),
    )
    bot_service = BotService(agent)

    try:
        run_polling_loop(telegram_client, bot_service, store, config)
    except KeyboardInterrupt:
        logger.info("Shutting down")


def run_polling_loop(telegram_client, bot_service, store, config: Config) -> None:
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

            if message.text.strip() == NEW_CHAT_COMMAND:
                try:
                    store.start_new_conversation(message.chat_id)
                except Exception:
                    logger.exception("Failed to start new conversation for chat %s", message.chat_id)
                    continue
                try:
                    telegram_client.send_message(message.chat_id, NEW_CHAT_REPLY)
                except TelegramAPIError:
                    logger.exception("Failed to send new-chat reply to chat %s", message.chat_id)
                continue

            with TypingIndicator(telegram_client, message.chat_id, config.typing_action_interval_seconds):
                try:
                    reply = bot_service.handle_message(message.chat_id, message.text)
                except Exception:
                    logger.exception("Failed to handle message for chat %s", message.chat_id)
                    reply = UNEXPECTED_ERROR_REPLY
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
