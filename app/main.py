"""Entry point: builds dependencies and runs the Telegram polling loop."""
from __future__ import annotations

import logging
import threading

from app.agent.loop import AgentLoop
from app.agent.system_prompt import build_system_prompt
from app.application.bot_service import BotService
from app.application.voice import EmptyTranscriptionError, VoiceProcessingError, VoiceProcessor
from app.config import Config, ConfigError, load_config
from app.dashboard.server import build_dashboard_server
from app.inference.ollama_chat import OllamaChatClient
from app.memory.store import ConversationStore
from app.stt.lemonade import LemonadeTranscriber
from app.telegram.client import TelegramAPIError, TelegramClient
from app.telegram.typing_indicator import TypingIndicator
from app.telegram.updates import CallbackQuery, TextMessage, VoiceMessage, parse_updates
from app.telemetry.broadcaster import EventBroadcaster
from app.telemetry.store import TraceStore
from app.telemetry.tracer import AgentTracer, NullTracer
from app.tools.exec_tool import ExecTool, build_exec_env

logger = logging.getLogger(__name__)

ACCESS_DENIED_REPLY = "Доступ ограничен."
NEW_CHAT_REPLY = "Начат новый диалог. Предыдущая история сохранена, но больше не используется как контекст."
VOICE_MODE_REPLY = "Режим голосовых сообщений включен."
STT_DISABLED_REPLY = "Распознавание голосовых сообщений сейчас отключено. Отправьте сообщение текстом."
VOICE_TOO_LONG_REPLY = "Голосовое сообщение слишком длинное. Максимум: 60 секунд."
VOICE_EMPTY_REPLY = "Не получилось разобрать голосовое сообщение. Попробуйте записать короче или отправьте текстом."
VOICE_TRANSCRIPTION_FAILED_REPLY = "Не получилось расшифровать голосовое сообщение. Попробуйте позже или отправьте текстом."
UNEXPECTED_ERROR_REPLY = "Произошла непредвиденная ошибка при обработке сообщения. Попробуйте ещё раз."
NEW_CHAT_COMMAND = "/new"
CONTROL_REPLY_MARKUP = {
    "inline_keyboard": [
        [
            {"text": "New", "callback_data": "mode:new"},
            {"text": "Voice", "callback_data": "mode:voice"},
        ]
    ]
}


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

    trace_store = None
    broadcaster = EventBroadcaster()
    tracer = NullTracer()
    if config.trace_enabled or config.dashboard_enabled:
        trace_store = TraceStore(config.memory_db_path)
    if config.trace_enabled and trace_store is not None:
        tracer = AgentTracer(
            trace_store, broadcaster, secrets=[config.telegram_bot_token, config.email_app_password]
        )

    agent = AgentLoop(
        chat_client=chat_client,
        tool=exec_tool,
        store=store,
        max_steps=config.agent_max_steps,
        max_context_messages=config.max_context_messages,
        system_prompt=build_system_prompt(),
        model=config.ollama_model,
        tracer=tracer,
    )
    bot_service = BotService(agent)
    voice_processor = None
    if config.stt_enabled:
        transcriber = LemonadeTranscriber(
            base_url=config.stt_base_url,
            model=config.stt_model,
            timeout_seconds=config.stt_timeout_seconds,
        )
        voice_processor = VoiceProcessor(transcriber=transcriber)

    dashboard_server = None
    if config.dashboard_enabled and trace_store is not None:
        try:
            dashboard_server = build_dashboard_server(
                config.dashboard_host, config.dashboard_port, trace_store, broadcaster, config.trace_max_list_limit
            )
            threading.Thread(target=dashboard_server.serve_forever, daemon=True).start()
            logger.info("Dashboard listening on http://%s:%s", config.dashboard_host, config.dashboard_port)
        except OSError:
            logger.exception("Failed to start dashboard server; continuing without it")
            dashboard_server = None

    try:
        run_polling_loop(telegram_client, bot_service, store, config, voice_processor=voice_processor)
    except KeyboardInterrupt:
        logger.info("Shutting down")
    finally:
        if dashboard_server is not None:
            dashboard_server.shutdown()
            dashboard_server.server_close()


def _is_new_chat_command(text: str) -> bool:
    """True for `/new`, including Telegram's group form `/new@botname` and trailing arguments."""
    first_token = text.strip().split(maxsplit=1)[0] if text.strip() else ""
    return first_token.split("@", 1)[0] == NEW_CHAT_COMMAND


def run_polling_loop(telegram_client, bot_service, store, config: Config, voice_processor=None) -> None:
    offset: int | None = None
    logger.info("Starting polling loop")
    while True:
        try:
            payload = telegram_client.get_updates(offset)
        except TelegramAPIError:
            logger.exception("Failed to fetch updates, retrying")
            continue

        raw_updates = payload.get("result", [])

        for event in parse_updates(payload):
            if config.allowed_chat_id is not None and event.chat_id != config.allowed_chat_id:
                logger.warning("Ignoring message from disallowed chat_id=%s", event.chat_id)
                if isinstance(event, CallbackQuery):
                    _answer_callback_query(telegram_client, event.callback_query_id)
                try:
                    _send_reply(telegram_client, event.chat_id, ACCESS_DENIED_REPLY)
                except TelegramAPIError:
                    logger.exception("Failed to send access-denied reply to chat %s", event.chat_id)
                continue

            if isinstance(event, CallbackQuery):
                _handle_callback_query(telegram_client, store, event, config)
                continue

            if isinstance(event, TextMessage) and _is_new_chat_command(event.text):
                try:
                    store.start_new_conversation(event.chat_id)
                    store.set_chat_input_mode(event.chat_id, "text")
                    reply = NEW_CHAT_REPLY
                except Exception:
                    logger.exception("Failed to start new conversation for chat %s", event.chat_id)
                    reply = UNEXPECTED_ERROR_REPLY
                try:
                    _send_reply(telegram_client, event.chat_id, reply)
                except TelegramAPIError:
                    logger.exception("Failed to send new-chat reply to chat %s", event.chat_id)
                continue

            if isinstance(event, VoiceMessage):
                _handle_voice_message(telegram_client, bot_service, event, config, voice_processor)
                continue

            with TypingIndicator(telegram_client, event.chat_id, config.typing_action_interval_seconds):
                try:
                    reply = bot_service.handle_message(event.chat_id, event.text)
                except Exception:
                    logger.exception("Failed to handle message for chat %s", event.chat_id)
                    reply = UNEXPECTED_ERROR_REPLY
            try:
                _send_reply(telegram_client, event.chat_id, reply)
            except TelegramAPIError:
                logger.exception("Failed to send reply to chat %s", event.chat_id)

        if raw_updates:
            last_update_id = raw_updates[-1].get("update_id")
            if isinstance(last_update_id, int):
                offset = last_update_id + 1


def _send_reply(telegram_client, chat_id: int, text: str) -> None:
    telegram_client.send_message(chat_id, text, reply_markup=CONTROL_REPLY_MARKUP)


def _answer_callback_query(telegram_client, callback_query_id: str) -> None:
    try:
        telegram_client.answer_callback_query(callback_query_id)
    except TelegramAPIError:
        logger.exception("Failed to answer callback query %s", callback_query_id)


def _handle_callback_query(telegram_client, store, event: CallbackQuery, config: Config) -> None:
    _answer_callback_query(telegram_client, event.callback_query_id)
    if event.data == "mode:voice":
        if not config.stt_enabled:
            try:
                _send_reply(telegram_client, event.chat_id, STT_DISABLED_REPLY)
            except TelegramAPIError:
                logger.exception("Failed to send STT-disabled callback reply to chat %s", event.chat_id)
            return
        try:
            store.set_chat_input_mode(event.chat_id, "voice")
            reply = VOICE_MODE_REPLY
        except Exception:
            logger.exception("Failed to switch chat %s to voice mode", event.chat_id)
            reply = UNEXPECTED_ERROR_REPLY
    else:
        try:
            store.start_new_conversation(event.chat_id)
            store.set_chat_input_mode(event.chat_id, "text")
            reply = NEW_CHAT_REPLY
        except Exception:
            logger.exception("Failed to start new conversation for chat %s", event.chat_id)
            reply = UNEXPECTED_ERROR_REPLY
    try:
        _send_reply(telegram_client, event.chat_id, reply)
    except TelegramAPIError:
        logger.exception("Failed to send callback reply to chat %s", event.chat_id)


def _handle_voice_message(telegram_client, bot_service, event: VoiceMessage, config: Config, voice_processor) -> None:
    if not config.stt_enabled:
        try:
            _send_reply(telegram_client, event.chat_id, STT_DISABLED_REPLY)
        except TelegramAPIError:
            logger.exception("Failed to send STT-disabled reply to chat %s", event.chat_id)
        return

    if event.duration > config.voice_max_duration_seconds:
        reply = f"Голосовое сообщение слишком длинное. Максимум: {config.voice_max_duration_seconds} секунд."
        try:
            _send_reply(telegram_client, event.chat_id, reply)
        except TelegramAPIError:
            logger.exception("Failed to send voice-duration reply to chat %s", event.chat_id)
        return

    with TypingIndicator(telegram_client, event.chat_id, config.typing_action_interval_seconds):
        try:
            file_info = telegram_client.get_file(event.file_id)
            file_path = file_info.get("file_path")
            if not isinstance(file_path, str) or not file_path:
                raise VoiceProcessingError("Telegram file_path missing")
            audio_bytes = telegram_client.download_file(file_path)
            if voice_processor is None:
                raise VoiceProcessingError("voice processor is not configured")
            text = voice_processor.process(audio_bytes)
            reply = bot_service.handle_message(event.chat_id, text)
        except EmptyTranscriptionError:
            logger.exception("Voice transcription was empty for chat %s", event.chat_id)
            reply = VOICE_EMPTY_REPLY
        except (TelegramAPIError, VoiceProcessingError):
            logger.exception("Failed to transcribe voice message for chat %s", event.chat_id)
            reply = VOICE_TRANSCRIPTION_FAILED_REPLY
        except Exception:
            logger.exception("Failed to handle transcribed voice message for chat %s", event.chat_id)
            reply = UNEXPECTED_ERROR_REPLY

    try:
        _send_reply(telegram_client, event.chat_id, reply)
    except TelegramAPIError:
        logger.exception("Failed to send voice reply to chat %s", event.chat_id)


if __name__ == "__main__":
    main()
