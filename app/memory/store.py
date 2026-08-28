"""SQLite-backed conversation memory: one active conversation per chat, trimmed by message count."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StoredMessage:
    role: str
    content: str


class ConversationStore:
    def __init__(self, db_path: str) -> None:
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(db_path, check_same_thread=False)
        self._init_schema()

    def _init_schema(self) -> None:
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                started_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL REFERENCES conversations(id),
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_settings (
                chat_id INTEGER PRIMARY KEY,
                input_mode TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        self._connection.commit()

    def active_conversation_id(self, chat_id: int) -> int:
        row = self._connection.execute(
            "SELECT id FROM conversations WHERE chat_id = ? ORDER BY id DESC LIMIT 1",
            (chat_id,),
        ).fetchone()
        if row is not None:
            return row[0]
        return self.start_new_conversation(chat_id)

    def start_new_conversation(self, chat_id: int) -> int:
        cursor = self._connection.execute(
            "INSERT INTO conversations (chat_id) VALUES (?)", (chat_id,)
        )
        self.set_chat_input_mode(chat_id, "text", commit=False)
        self._connection.commit()
        return cursor.lastrowid

    def append_message(self, conversation_id: int, role: str, content: str) -> None:
        self._connection.execute(
            "INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)",
            (conversation_id, role, content),
        )
        self._connection.commit()

    def recent_messages(self, conversation_id: int, limit: int) -> list[StoredMessage]:
        rows = self._connection.execute(
            """
            SELECT role, content FROM messages
            WHERE conversation_id = ?
            ORDER BY id DESC LIMIT ?
            """,
            (conversation_id, limit),
        ).fetchall()
        return [StoredMessage(role=role, content=content) for role, content in reversed(rows)]

    def chat_input_mode(self, chat_id: int) -> str:
        row = self._connection.execute(
            "SELECT input_mode FROM chat_settings WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()
        if row is None:
            return "text"
        return row[0]

    def set_chat_input_mode(self, chat_id: int, input_mode: str, commit: bool = True) -> None:
        if input_mode not in {"text", "voice"}:
            raise ValueError(f"unsupported input_mode: {input_mode}")
        self._connection.execute(
            """
            INSERT INTO chat_settings (chat_id, input_mode, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(chat_id) DO UPDATE SET
                input_mode = excluded.input_mode,
                updated_at = excluded.updated_at
            """,
            (chat_id, input_mode),
        )
        if commit:
            self._connection.commit()
