# -*- coding: utf-8 -*-
"""Подробности по ответу оператора: событие, текст, куда он делся в панели."""
import json
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

print("== события reply_sent за сутки ==")
with store._lock:
    ряды = store._conn.execute(
        "SELECT id, created_at, message_id, recipient_id, "
        "COALESCE(detail_json,'') FROM events "
        "WHERE event_type='reply_sent' AND created_at >= "
        "datetime('now','-1 day') ORDER BY created_at DESC").fetchall()
for eid, ts, mid, rcid, dj in ряды:
    print(f"  событие #{eid} {ts[:19]} message_id={mid} recipient={rcid}")
    print(f"    {dj[:400]}")

print("\n== строка ответа в очереди ==")
row = store.confirm_get(3052) or {}
for k in ("id", "kind", "status", "email", "subject", "message_id",
          "decided_by", "created_at", "updated_at"):
    print(f"  {k}: {row.get(k)!r}")
print("\n  тело:")
print("   ", (row.get("body") or "")[:600].replace("\n", "\n    "))

print("\n== есть ли письмо в messages у этого получателя ==")
rcid = row.get("recipient_id")
with store._lock:
    ряды2 = store._conn.execute(
        "SELECT id, status, COALESCE(subject,''), COALESCE(sent_at,''), "
        "COALESCE(in_reply_to,'') FROM messages WHERE recipient_id=? "
        "ORDER BY id DESC LIMIT 10", (rcid,)).fetchall()
for mid, st, тема, отпр, отв in ряды2:
    print(f"  #{mid} {st:<12} {тема[:44]:<46} {отпр[:19] or '—'} "
          f"{'(ответ)' if отв else ''}")
if not ряды2:
    print("  писем этому получателю в messages НЕТ")
