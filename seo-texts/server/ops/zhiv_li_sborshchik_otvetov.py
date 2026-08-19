# -*- coding: utf-8 -*-
"""Жив ли сборщик входящих и что мы ответили — чтобы «ответа нет» было фактом.

«Он не ответил» и «мы перестали читать почту» с виду одинаковы. Поэтому
рядом с проверкой конкретного диалога смотрим, когда вообще приходило
последнее входящее: если поток жив, молчание — это молчание.
"""
import json
import re
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                       # noqa: E402
from sender.store import Store                                         # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))


def _т(s, n=1500):
    s = re.sub(r"<br\s*/?>", "\n", str(s or ""), flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"[ \t]+", " ", s)
    return re.sub(r"\n\s*\n+", "\n", s).strip()[:n]


print("== последние входящие (весь ящик, любые компании) ==")
with store._lock:
    посл = store._conn.execute(
        "SELECT e.event_type, e.event_ts, r.company_name, r.email "
        "FROM events e LEFT JOIN recipients r ON r.id=e.recipient_id "
        "WHERE e.event_type IN ('reply','reply_auto') "
        "ORDER BY e.event_ts DESC LIMIT 8").fetchall()
for e in посл:
    print(f"  {str(e['event_ts'])[:16]}  {e['event_type']:<11} "
          f"{(e['company_name'] or '—')[:38]} <{e['email']}>")

print("\n== наш ответ этой компании (reply_sent) ==")
with store._lock:
    отв = store._conn.execute(
        "SELECT e.id, e.event_ts, e.mailbox_id, e.detail_json "
        "FROM events e WHERE e.recipient_id=? AND e.event_type='reply_sent' "
        "ORDER BY e.event_ts", (int(sys.argv[1]),)).fetchall()
for e in отв:
    d = {}
    try:
        d = json.loads(e["detail_json"] or "{}")
    except Exception:                                                  # noqa: BLE001
        pass
    print(f"  {str(e['event_ts'])[:16]} с {e['mailbox_id']}")
    print(f"  ключи детали: {sorted(d.keys())}")
    if d.get("subject"):
        print(f"  тема: {_т(d['subject'], 120)}")
    тело = d.get("body") or d.get("text") or ""
    if тело:
        for л in _т(тело).split("\n"):
            if л.strip():
                print(f"    | {л.strip()[:150]}")
    else:
        print("    (текста в событии нет)")

print("\n== входящие ПОСЛЕ нашего ответа ==")
with store._lock:
    после = store._conn.execute(
        "SELECT event_type, event_ts FROM events WHERE recipient_id=? "
        "AND event_ts > (SELECT MAX(event_ts) FROM events "
        "                WHERE recipient_id=? AND event_type='reply_sent') "
        "ORDER BY event_ts", (int(sys.argv[1]), int(sys.argv[1]))).fetchall()
if not после:
    print("  НЕТ НИ ОДНОГО события после нашего ответа")
for e in после:
    print(f"  {str(e['event_ts'])[:16]}  {e['event_type']}")
