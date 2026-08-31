# -*- coding: utf-8 -*-
"""Что именно смутило линзу в 12173 и 12174: карточка против текста письма."""
import json
import sqlite3
import textwrap

s = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=60)
s.row_factory = sqlite3.Row
e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=60)
e.row_factory = sqlite3.Row

for rid_ in (12173, 12174):
    r = s.execute("SELECT id, recipient_id, inn, email, subject, body, "
                  "       edited_subject, edited_body FROM confirm_reviews "
                  " WHERE id=?", (rid_,)).fetchone()
    q = s.execute("SELECT company_name, okved, contact_name, extra_json, inn, "
                  "       domain FROM recipients WHERE id=?",
                  (r["recipient_id"],)).fetchone()
    доп = {}
    try:
        доп = json.loads(q["extra_json"] or "{}") or {}
    except Exception:                                         # noqa: BLE001
        pass
    к = e.execute("SELECT name, short_name, okved, okved_all, site, activity, "
                  "       region, revenue_rub, site_title, site_description "
                  "  FROM companies WHERE inn=?", (q["inn"],)).fetchone()
    print("\n################ review %d ################" % rid_)
    print("карточка панели: %s | ОКВЭД %s | домен %s"
          % (q["company_name"], q["okved"], q["domain"]))
    if к:
        print("обогащение: %s | ОКВЭД %s | сайт %s | регион %s | выручка %s"
              % (к["short_name"] or к["name"], к["okved"], к["site"],
                 к["region"], к["revenue_rub"]))
        print("  activity: %s" % str(к["activity"] or "")[:200])
        print("  title:    %s" % str(к["site_title"] or "")[:160])
        print("  descr:    %s" % str(к["site_description"] or "")[:200])
        print("  окведы:   %s" % str(к["okved_all"] or "")[:200])
    пасп = доп.get("site_facts")
    print("  паспорт сайта в карточке: %s"
          % (json.dumps(пасп, ensure_ascii=False)[:300] if пасп else "НЕТ"))
    print("  тема: %s" % ((r["edited_subject"] or "").strip() or r["subject"]))
    тело = (r["edited_body"] or "").strip() or r["body"] or ""
    print("  ----- письмо -----")
    for с in тело.splitlines():
        for кус in (textwrap.wrap(с, 96) or [""]):
            print("  | %s" % кус)
s.close()
e.close()
