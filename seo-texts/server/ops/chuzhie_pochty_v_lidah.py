# -*- coding: utf-8 -*-
"""Откуда в карточках лидов взялись чужие адреса и как проскочил конкурент."""
import json
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
c.row_factory = sqlite3.Row

print("=== две карточки с чужими адресами ===")
for инн in ("5503246419", "6617028416"):
    r = c.execute("SELECT id, email, company_name, domain FROM recipients "
                  " WHERE inn=?", (инн,)).fetchone()
    if r is None:
        print("   ИНН %s — получателя нет" % инн)
        continue
    print("")
    print("   %s (ИНН %s)" % (r["company_name"], инн))
    print("      писали на: %s  (домен карточки %s)" % (r["email"], r["domain"]))
    for l in c.execute("SELECT id, email, reply_kind, thread_id, created_at, "
                       "       substr(need,1,90) n FROM leads WHERE recipient_id=?",
                       (r["id"],)):
        print("      лид #%s: адрес %s | вид %s | %s"
              % (l["id"], l["email"], l["reply_kind"], str(l["created_at"])[:19]))
        print("         %s" % str(l["n"]).replace("\n", " ")[:90])
    for e in c.execute("SELECT id, event_type, event_ts, detail_json FROM events "
                       " WHERE recipient_id=? AND event_type IN ('reply','reply_auto') "
                       " ORDER BY event_ts DESC LIMIT 3", (r["id"],)):
        d = json.loads(e["detail_json"] or "{}")
        print("      событие %s %s: от %s | %s"
              % (e["event_type"], str(e["event_ts"])[:19],
                 d.get("from") or d.get("otvetil") or d.get("sender") or "?",
                 " ".join(str(d.get("snippet") or "").split())[:70]))
        print("         ключи detail: %s" % ", ".join(sorted(d)[:14]))

print("")
print("=== конкурент erk-ekb.ru ===")
for r in c.execute("SELECT id, inn, email, company_name, domain, okved, "
                   "       COALESCE(extra_json,'') e FROM recipients "
                   " WHERE email LIKE '%erk-ekb%' OR domain LIKE '%erk-ekb%' "
                   "    OR company_name LIKE '%нергоремкомплект%'"):
    print("   #%s %s (ИНН %s)" % (r["id"], r["company_name"], r["inn"]))
    print("      адрес %s | домен %s | ОКВЭД %s" % (r["email"], r["domain"], r["okved"]))
    print("      extra: %s" % str(r["e"])[:300])
    for cr in c.execute("SELECT id, status, reason, created_at, substr(subject,1,60) s "
                        " FROM confirm_reviews WHERE recipient_id=? "
                        " ORDER BY id DESC LIMIT 3", (r["id"],)):
        print("      карточка #%s %s %s | %s" % (cr["id"], cr["status"],
                                                 str(cr["created_at"])[:19], cr["s"]))
c.close()
