#!/usr/bin/env python3
from __future__ import annotations

import imaplib
import os


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
        print(f"unread={len(data[0].split())}")
    finally:
        conn.logout()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
