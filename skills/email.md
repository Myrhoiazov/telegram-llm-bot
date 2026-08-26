# Скилл: проверка почты (IMAP)

Тип: инструкция к работе с почтовым сервером по протоколу IMAP через стандартную библиотеку Python
(`imaplib`), без сторонних зависимостей.

## Требования

Переменные окружения `EMAIL_IMAP_HOST`, `EMAIL_IMAP_PORT`, `EMAIL_ADDRESS`, `EMAIL_APP_PASSWORD` должны
быть заданы в `.env` бота. Если они не заданы, скрипт ниже сам сообщит об этом строкой
`email_not_configured` — в этом случае скажи пользователю, что почта не настроена, и не придумывай данные.

## Как использовать

Выполни через execute_command:

```
python3 -c "
import imaplib, os, sys

host = os.environ.get('EMAIL_IMAP_HOST')
user = os.environ.get('EMAIL_ADDRESS')
password = os.environ.get('EMAIL_APP_PASSWORD')
if not host or not user or not password:
    print('email_not_configured')
    sys.exit(0)
port = int(os.environ.get('EMAIL_IMAP_PORT', '993'))
conn = imaplib.IMAP4_SSL(host, port)
conn.login(user, password)
conn.select('INBOX')
status, data = conn.search(None, 'UNSEEN')
ids = data[0].split()
print(f'unread={len(ids)}')
for msg_id in ids[:5]:
    status, msg_data = conn.fetch(msg_id, '(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)])')
    header = msg_data[0][1].decode(errors='replace').strip()
    print(header.replace(chr(10), ' | '))
conn.logout()
"
```

Вывод: первая строка — `unread=<N>` (число непрочитанных писем), затем до 5 строк с полями `From`/`Subject`
непрочитанных писем, разделёнными ` | `. `BODY.PEEK` не помечает письма как прочитанные.
