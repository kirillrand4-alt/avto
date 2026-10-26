# -*- coding: utf-8 -*-
"""Почему «Отправлено» в ёмкости пулов не бьётся с «Динамикой»: считаем источники. Только чтение."""
import sqlite3
import sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store    # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
st = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
сумма, ключи = 0, set()
for mb in cfg.mailboxes():
    s = st.get_mailbox_state(mb.mailbox_id)
    if s and mb.division == "meyer":
        сумма += int(s.sent_today or 0)
        ключи.add(str(getattr(s, "day_key", "")))
print("Meyer sent_today (счётчик ящиков):", сумма, "day_key:", ключи)
for d in ("date('now')",):
    print("писем sent за UTC-сегодня:", c.execute("SELECT COUNT(*) FROM messages WHERE status='sent' AND sent_at >= date('now')").fetchone()[0])
    print("писем sent с 00:00 МСК:", c.execute("SELECT COUNT(*) FROM messages WHERE status='sent' AND sent_at >= datetime(date('now','+3 hours'),'-3 hours')").fetchone()[0])
    print("событий sent за UTC-сегодня:", c.execute("SELECT COUNT(*) FROM events WHERE event_type='sent' AND event_ts >= date('now')").fetchone()[0])
    print("reply_sent за UTC-сегодня:", c.execute("SELECT COUNT(*) FROM events WHERE event_type='reply_sent' AND event_ts >= date('now')").fetchone()[0])
    print("карточек-ответов sent за UTC-сегодня:", c.execute("SELECT COUNT(*) FROM confirm_reviews WHERE kind='reply' AND status='sent' AND decided_at >= date('now')").fetchone()[0])
print("вернули по правилам:", c.execute("SELECT COUNT(*) FROM messages WHERE id IN (SELECT 0)").fetchone()[0])
