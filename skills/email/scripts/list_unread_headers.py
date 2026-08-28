#!/usr/bin/env python3
from __future__ import annotations

import email.header
import imaplib
import os
import sys
from email.parser import BytesParser


MAX_MESSAGES = 10


def decode_mime_header(value) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r", " ").replace("\n", " ")
    text = " ".join(text.split())
    try:
        decoded = str(email.header.make_header(email.header.decode_header(text)))
    except (LookupError, UnicodeDecodeError, email.errors.HeaderParseError):
        decoded = text
    return " ".join(decoded.replace("\xa0", " ").split())


def parse_header_message(msg_id: bytes, raw: bytes) -> dict[str, str]:
    msg = BytesParser().parsebytes(raw)
    return {
        "id": msg_id.decode(errors="replace"),
        "from": decode_mime_header(msg.get("From")),
        "subject": decode_mime_header(msg.get("Subject")),
        "date": decode_mime_header(msg.get("Date")),
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
        print(f"unread={len(ids)}")
        for msg_id in ids[:MAX_MESSAGES]:
            _status, msg_data = conn.fetch(msg_id, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            parsed = parse_header_message(msg_id, msg_data[0][1])
            print("id=" + parsed["id"])
            print("from=" + parsed["from"])
            print("subject=" + parsed["subject"])
            print("date=" + parsed["date"])
            print("---")
    finally:
        conn.logout()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
