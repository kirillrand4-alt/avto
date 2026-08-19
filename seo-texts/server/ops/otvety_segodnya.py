# -*- coding: utf-8 -*-
"""Входящие ответы за сегодня: кто ответил, о чём, и ответили ли ему.

Владелец: «сегодня один ответ был про 2 компрессора, мы ему написали,
посмотри ответил ли он». Ищем ответ по тексту, дальше разворачиваем ВЕСЬ
разговор с этой компанией по времени: наши письма, их ответы, наши ответы.
"""
import json
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                       # noqa: E402
from sender.store import Store                                         # noqa: E402

ИСКАТЬ = sys.argv[1] if len(sys.argv) > 1 else "компрессор"
ДНЕЙ = int(next((a for a in sys.argv[1:] if a.isdigit()), "1"))

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))


def _текст(s, лимит=400):
    s = re.sub(r"<[^>]+>", " ", str(s or ""))
    s = re.sub(r"\s+", " ", s).strip()
    return s[:лимит]


print(f"== входящие ответы за последние {ДНЕЙ} дн. ==")
with store._lock:
    события = store._conn.execute(
        "SELECT e.id, e.event_type, e.event_ts, e.recipient_id, e.mailbox_id, "
        "       e.detail_json, r.email, r.company_name, r.inn "
        "FROM events e LEFT JOIN recipients r ON r.id=e.recipient_id "
        "WHERE e.event_type IN ('reply','reply_auto') "
        "AND date(e.event_ts) >= date('now', ?) "
        "ORDER BY e.event_ts", (f"-{ДНЕЙ} day",)).fetchall()

print(f"всего ответов: {len(события)}")
совпали = []
for e in события:
    d = {}
    try:
        d = json.loads(e["detail_json"] or "{}")
    except Exception:                                                  # noqa: BLE001
        pass
    тело = _текст(d.get("body") or d.get("text") or d.get("snippet") or "")
    тема = _текст(d.get("subject") or "", 90)
    метка = f"{str(e['event_ts'])[11:16]} {e['company_name'] or '—'} <{e['email']}>"
    print(f"\n  [{e['event_type']}] {метка}")
    if тема:
        print(f"     тема: {тема}")
    if тело:
        print(f"     текст: {тело[:260]}")
    if ИСКАТЬ.lower() in (тело + " " + тема).lower():
        совпали.append(e)

print(f"\n== содержат «{ИСКАТЬ}»: {len(совпали)} ==")
for e in совпали:
    print(f"  recipient_id={e['recipient_id']} {e['company_name']} <{e['email']}>")
