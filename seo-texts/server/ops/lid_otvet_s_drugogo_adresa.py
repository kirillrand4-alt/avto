# -*- coding: utf-8 -*-
"""Лид из ответа, пришедшего с ДРУГОГО адреса (не того, куда писали), поэтому
панель не связала его с перепиской. Привязываем к нашему письму и компании.

    lid_otvet_s_drugogo_adresa.py <event_id> <message_id> <телефон> "<контакт>"
"""
import json
import sqlite3
import sys
sys.path.insert(0, r"C:\sender")
from sender.store import Store  # noqa: E402
eid, mid, тел, контакт = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3], sys.argv[4]
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
е = c.execute("SELECT * FROM events WHERE id=?", (eid,)).fetchone()
d = json.loads(е["detail_json"] or "{}")
h = d.get("headers") or {}
import re  # noqa: E402
адрес = (re.findall(r"[\w.+-]+@[\w.-]+", str(h.get("From") or "")) or [""])[0].lower()
м = c.execute("SELECT * FROM messages WHERE id=?", (mid,)).fetchone()
р = c.execute("SELECT * FROM recipients WHERE id=?", (м["recipient_id"],)).fetchone()
кол = м.keys()
тред = м["thread_id"] if "thread_id" in кол else None
store = Store(r"C:\sender\sender.db")
лид, создан = store.create_lead(
    email=адрес, dedup_key="otvet-s-drugogo:%d" % eid, recipient_id=р["id"], campaign_id=м["campaign_id"],
    thread_id=тред, company_name=р["company_name"], inn=р["inn"], reply_kind="interested", phone=тел,
    need="%s ответил с другого адреса (%s) на наше письмо #%d от %s на %s («%s»): «%s»"
         % (контакт, адрес, mid, (м["sent_at"] or "")[:16], р["email"], м["subject"],
            str(d.get("snippet") or d.get("text") or "")[:600]),
    readiness="просит материалы и ссылки по рентген-контролю", source_event_id=eid)
print("лид #%s %s: %s, ИНН %s, контакт %s %s %s" % (лид, "заведён" if создан else "уже был",
      р["company_name"], р["inn"], контакт, адрес, тел))
print("текст: %s" % str(d.get("snippet") or d.get("text") or "")[:300])
print("=== ЛИД С ДРУГОГО АДРЕСА ===")
