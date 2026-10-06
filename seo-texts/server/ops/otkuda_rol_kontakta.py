# -*- coding: utf-8 -*-
"""Откуда у контакта взялась роль: происхождение строки в карточке письма.

В панели «кто это» — это contact.role. Рядом в карточке лежат поля
происхождения (source, source_label, source_url, provenance), и по ним
видно, откуда роль пришла: с сайта, из базы обзвона, из площадки или её
просто предположили.
"""
import json
import os
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

ПИСЬМО = int(sys.argv[1]) if len(sys.argv) > 1 else 12570
store = Store(r"C:\sender\sender.db")
with store._lock:
    # #N в панели — номер карточки очереди (confirm_reviews.id)
    кол = [x[1] for x in store._conn.execute(
        "PRAGMA table_info(confirm_reviews)")]
    поля = ["id", "panel_json"] + [x for x in ("inn", "email", "company_name",
                                               "campaign_id", "message_id")
                                   if x in кол]
    р = store._conn.execute(
        "SELECT %s FROM confirm_reviews WHERE id=?" % ", ".join(поля),
        (ПИСЬМО,)).fetchone()
if not р:
    raise SystemExit("письма %s нет" % ПИСЬМО)
print("карточка #%s: %s" % (р["id"], "; ".join(
    "%s=%s" % (к, str(р[к])[:40]) for к in поля if к != "panel_json")))
д = json.loads(р["panel_json"] or "{}")
к = д.get("contact") or {}
print("")
print("--- блок «кому пишем» (contact) ---")
for поле in sorted(к):
    з = к[поле]
    if з not in (None, "", []):
        print("   %-22s %s" % (поле, str(з)[:110]))

# что лежит в обогащении про этот адрес
путь = r"C:\sender\enrich.db"
if os.path.exists(путь):
    cx = sqlite3.connect("file:%s?mode=ro" % путь, uri=True)
    cx.row_factory = sqlite3.Row
    кол = [x[1] for x in cx.execute("PRAGMA table_info(emails)")]
    инн = str((д.get("company") or {}).get("inn") or "")
    print("")
    print("--- что в обогащении про адреса ИНН %s ---" % инн)
    print("   колонки emails: %s" % ", ".join(кол))
    for стр in cx.execute("SELECT * FROM emails WHERE inn=?", (инн,)):
        куски = []
        for поле in кол:
            if стр[поле] not in (None, "", 0):
                куски.append("%s=%s" % (поле, str(стр[поле])[:60]))
        print("   " + "; ".join(куски))
    cx.close()
print("")
print("=" * 74)
print("=== ОТКУДА РОЛЬ КОНТАКТА ===")
