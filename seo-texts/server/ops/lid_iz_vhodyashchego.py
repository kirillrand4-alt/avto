# -*- coding: utf-8 -*-
"""Завести лид из входящего «вне переписки» (событие), чтобы он был виден в ленте.

    lid_iz_vhodyashchego.py <event_id> <телефон> "<кандидаты/примечание>" [inn]
"""
import json
import re
import sqlite3
import sys
sys.path.insert(0, r"C:\sender")
from sender.store import Store  # noqa: E402
eid, тел, прим = int(sys.argv[1]), sys.argv[2], sys.argv[3]
инн = sys.argv[4] if len(sys.argv) > 4 else None
store = Store(r"C:\sender\sender.db")
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
е = c.execute("SELECT * FROM events WHERE id=?", (eid,)).fetchone()
d = json.loads(е["detail_json"] or "{}")
h = d.get("headers") or {}
адрес = (re.findall(r"[\w.+-]+@[\w.-]+", str(h.get("From") or "")) or [""])[0].lower()
имя = str(h.get("From") or "").split("<")[0].strip()
rid = None
компания = "%s — переслали письмо (%s)" % (имя or адрес, прим)
if инн:
    р = c.execute("SELECT id, company_name FROM recipients WHERE inn=? ORDER BY id DESC LIMIT 1", (инн,)).fetchone()
    if р:
        rid, компания = р["id"], р["company_name"]
лид, создан = store.create_lead(
    email=адрес, dedup_key="vne-perepiski:%d" % eid, recipient_id=rid, company_name=компания, inn=инн,
    reply_kind="interested", phone=тел,
    need="Входящее вне переписки на %s: «%s»" % (е["mailbox_id"], str(d.get("snippet") or "")[:600]),
    source_event_id=eid)
print("лид #%s %s; компания: %s" % (лид, "заведён" if создан else "уже был", компания))
print("=== ЛИД ИЗ ВХОДЯЩЕГО ===")
