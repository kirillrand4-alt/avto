# -*- coding: utf-8 -*-
"""Только чтение: найти письмо про РМЗ и посмотреть, как оно возникло."""
import json
import sqlite3

s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row
ряды = list(s.execute(
    "SELECT id, campaign_id, recipient_id, inn, email, subject, status,"
    " created_at, decided_by, decided_at, panel_json, body"
    " FROM confirm_reviews WHERE body LIKE '%РМЗ%'"
    " AND body LIKE '%посторонних включени%' ORDER BY id DESC LIMIT 5"))
print("=== НАЙДЕНО КАРТОЧЕК: %d ===" % len(ряды))
for р in ряды:
    print("\n  #%s камп %s | статус %s | %s" % (р["id"], р["campaign_id"],
                                                р["status"], р["email"]))
    print("     ИНН %s | создано %s | решил %s в %s"
          % (р["inn"], str(р["created_at"])[:19], р["decided_by"],
             str(р["decided_at"])[:19]))
    print("     тема: %s" % р["subject"])
    try:
        p = json.loads(р["panel_json"] or "{}")
        print("     panel ключи: %s" % sorted(p.keys())[:16])
        for k in ("letter_division", "model", "модель", "napravlenie", "linza",
                  "лизна", "линза", "gate", "проверки"):
            if k in p:
                print("       %-18s %s" % (k, str(p[k])[:110]))
    except Exception as ex:
        print("     panel не разобрался: %s" % str(ex)[:60])

if ряды:
    р = ряды[0]
    print("\n=== КАРТОЧКА КОМПАНИИ ===")
    rec = s.execute("SELECT id, inn, company_name, okved, segment, region, domain,"
                    " extra_json FROM recipients WHERE id=?",
                    (р["recipient_id"],)).fetchone()
    if rec:
        for k in ("inn", "company_name", "okved", "segment", "region", "domain"):
            print("  %-14s %s" % (k, str(rec[k])[:96]))
        try:
            ex = json.loads(rec["extra_json"] or "{}")
            print("  extra ключи: %s" % sorted(ex.keys()))
            for k in ("division", "target_division", "ne_nash_ni_odnomu",
                      "gruppy", "predprosev_otkat_26_08"):
                if k in ex:
                    print("    %-24s %s" % (k, str(ex[k])[:100]))
        except Exception:
            pass

    print("\n=== ПАСПОРТ САЙТА ===")
    e = sqlite3.connect("file:C:/sender/enrich.db?mode=ro", uri=True)
    e.row_factory = sqlite3.Row
    ф = e.execute("SELECT site, facts_json FROM site_facts WHERE inn=?",
                  (str(rec["inn"]),)).fetchone() if rec else None
    if ф:
        print("  сайт: %s" % ф["site"])
        d = json.loads(ф["facts_json"] or "{}")
        for k, v in d.items():
            if v in (None, "", [], {}, "нет"):
                continue
            t = ", ".join(str(x) for x in v) if isinstance(v, list) else str(v)
            print("    %-22s %s" % (k, t[:96]))
    else:
        print("  паспорта нет")

print("\n=== ИТОГ ===")
print("  см. статус карточки и решившего выше")
