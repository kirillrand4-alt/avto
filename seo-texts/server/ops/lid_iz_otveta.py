# -*- coding: utf-8 -*-
"""Отдельный лид из ответа, который панель приклеила к чужому лиду той же компании
(владелец 14.10: «вот это письмо не вижу в панели» — Павленко, ООО «ТЭСТИ»).

    lid_iz_otveta.py <event_id> ["<примечание>"]
"""
import json
import re
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.store import Store  # noqa: E402

eid = int(sys.argv[1])
прим = sys.argv[2] if len(sys.argv) > 2 else ""
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
е = c.execute("SELECT * FROM events WHERE id=?", (eid,)).fetchone()
д = json.loads(е["detail_json"] or "{}")
h = д.get("headers") or {}
адрес = (re.findall(r"[\w.+-]+@[\w.-]+", str(h.get("From") or "")) or [""])[0].lower()
р = c.execute("SELECT * FROM recipients WHERE id=?", (е["recipient_id"],)).fetchone()
текст = re.split(r"-----Original Message-----|From:|От:", str(д.get("snippet") or ""))[0].strip()
store = Store(r"C:\sender\sender.db")
лид, создан = store.create_lead(
    email=адрес, dedup_key="otvet-otdelno:%d" % eid, recipient_id=р["id"], campaign_id=е["campaign_id"],
    company_name=р["company_name"], inn=р["inn"], reply_kind=д.get("reply_kind") or "interested",
    need=("Ответ %s на наше письмо (на %s): «%s»%s" % (адрес, р["email"], текст[:500], (" | " + прим) if прим else "")),
    source_event_id=eid)
print("лид #%s %s: %s, ИНН %s, %s" % (лид, "заведён" if создан else "уже был", р["company_name"], р["inn"], адрес))
print("=== ЛИД ИЗ ОТВЕТА ===")
