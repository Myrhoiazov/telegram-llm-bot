#!/usr/bin/env python3
from __future__ import annotations

import email
import imaplib
import json
import os
import re

from list_unread_headers import decode_mime_header


MAX_MESSAGES = 10


def text_from_message(msg) -> str:
    chunks: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_maintype() == "multipart":
                continue
            if part.get_content_disposition() == "attachment":
                continue
            if part.get_content_type() not in ("text/plain", "text/html"):
                continue
            payload = part.get_payload(decode=True)
            if payload:
                chunks.append(payload.decode(part.get_content_charset() or "utf-8", errors="replace"))
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            chunks.append(payload.decode(msg.get_content_charset() or "utf-8", errors="replace"))
    text = "\n".join(chunks)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:700]


def parse_full_message(msg_id: bytes, raw: bytes) -> dict[str, str]:
    msg = email.message_from_bytes(raw)
    return {
        "imap_id": msg_id.decode(errors="replace"),
        "from": decode_mime_header(msg.get("From")),
        "subject": decode_mime_header(msg.get("Subject")),
        "date": decode_mime_header(msg.get("Date")),
        "snippet": text_from_message(msg),
    }


def main() -> int:
    host = os.environ.get("EMAIL_IMAP_HOST")
    user = os.environ.get("EMAIL_ADDRESS")
    password = os.environ.get("EMAIL_APP_PASSWORD")
    if not host or not user or not password:
        print("email_not_configured")
        return 0

    port = int(os.environ.get("EMAIL_IMAP_PORT", "993"))
    conn = imaplib.IMAP4_SSL(host, port)
    try:
        conn.login(user, password)
        conn.select("INBOX")
        _status, data = conn.search(None, "UNSEEN")
        ids = data[0].split()
        items = []
        for msg_id in ids[:MAX_MESSAGES]:
            _status, msg_data = conn.fetch(msg_id, "(BODY.PEEK[])")
            items.append(parse_full_message(msg_id, msg_data[0][1]))
        print(json.dumps({"unread": len(ids), "items": items}, ensure_ascii=False))
    finally:
        conn.logout()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
