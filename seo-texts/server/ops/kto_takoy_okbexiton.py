# -*- coding: utf-8 -*-
"""Полный текст запроса с gi@okbexiton.ru и что мы знаем про эту компанию."""
import json
import sqlite3
БАЗА = r"C:\sender\sender.db"
ОБОГ = r"C:\sender\enrich.db"
ОБЗВОН = r"C:\sender\obzvon-index.db"
c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
c.row_factory = sqlite3.Row
for eid in (155308, 308536):
    r = c.execute("SELECT id, event_ts, mailbox_id, detail_json FROM events "
                  " WHERE id=?", (eid,)).fetchone()
    if not r:
        continue
    d = json.loads(r["detail_json"] or "{}")
    h = d.get("headers") or {}
    print("=" * 68)
    print("ev=%s  %s  на наш ящик %s" % (r["id"], str(r["event_ts"])[:19],
                                         r["mailbox_id"]))
    print("От:   %s" % str(h.get("From") or ""))
    print("Тема: %s" % str(h.get("Subject") or ""))
    print("-" * 68)
    print(str(d.get("snippet") or "")[:1400])
print("=" * 68)
print("\n=== есть ли okbexiton в получателях ===")
for r in c.execute("SELECT id, email, inn, company_name, segment FROM recipients "
                   " WHERE email LIKE '%okbexiton%' OR domain LIKE '%okbexiton%'"):
    print("   rid=%s %s ИНН %s %s (%s)" % (r["id"], r["email"], r["inn"],
                                           r["company_name"], r["segment"]))
print("\n=== писали ли мы им ===")
for r in c.execute("SELECT m.id, m.sent_at, r.email FROM messages m "
                   "  JOIN recipients r ON r.id=m.recipient_id "
                   " WHERE r.email LIKE '%okbexiton%'"):
    print("   msg=%s %s -> %s" % (r["id"], str(r["sent_at"])[:19], r["email"]))
c.close()
for имя, путь, запрос in (
        ("обогащение", ОБОГ,
         "SELECT inn, email, source, source_url FROM emails "
         " WHERE email LIKE '%okbexiton%' LIMIT 10"),
        ("обзвон", ОБЗВОН,
         "SELECT inn, name_short, site, region FROM obzvon "
         " WHERE site LIKE '%okbexiton%' LIMIT 10")):
    print("\n=== %s ===" % имя)
    try:
        x = sqlite3.connect("file:%s?mode=ro" % путь, uri=True, timeout=60)
        x.row_factory = sqlite3.Row
        нашли = False
        for r in x.execute(запрос):
            нашли = True
            print("   %s" % dict(r))
        if not нашли:
            print("   ничего")
        x.close()
    except Exception as ex:
        print("   %s" % ex)
