# -*- coding: utf-8 -*-
"""Единственный ответ, которому не нашлось компании: показать целиком.

Ни ветка, ни адрес не привязались — значит человек пишет с адреса, которого
нет в базе, а References почтовик срезал. Автоматом такое привязывать нельзя
(ошибёмся компанией), поэтому выкладываем всё, что о нём известно.
"""
import json
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
р = c.execute("SELECT * FROM events WHERE id=182154").fetchone()
if not р:
    raise SystemExit("события нет")
d = json.loads(р["detail_json"] or "{}")
з = d.get("headers") or {}
print("когда:   %s" % р["event_ts"])
print("в ящик:  %s" % (d.get("inbox_mailbox") or р["mailbox_id"]))
print("от кого: %s" % з.get("From"))
print("тема:    %s" % з.get("Subject"))
print("метка разбора: %s" % d.get("reply_kind"))
print("In-Reply-To:   %s" % (d.get("in_reply_to_hdr") or з.get("In-Reply-To") or "нет"))
print("\n--- текст ---")
print(str(d.get("snippet") or "")[:1500])

домен = str(з.get("From") or "").split("@")[-1].strip("<> ").lower()
print("\n--- кто в базе с домена %s ---" % домен)
for х in c.execute("SELECT id, email, company_name, inn FROM recipients "
                   " WHERE LOWER(email) LIKE ?", ("%@" + домен,)):
    print("   #%-6s %-30s %-34s %s" % (х["id"], х["email"],
                                       str(х["company_name"] or "")[:34], х["inn"]))
