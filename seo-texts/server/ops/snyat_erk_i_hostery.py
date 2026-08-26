# -*- coding: utf-8 -*-
"""Три точечных дела: конкурент в реестр, два адреса хостера — из базы.

1. ООО «Энергоремкомплект» (erk-ekb.ru) — делает поршневые компрессоры и
   запчасти к ним. Заводим в реестр «не наш адресат»: это ровно тот повод,
   ради которого реестр и создан — «компания сама производит то, что мы
   продаём».
2. support@sweb.ru у «Прод-Маркета» и info@timeweb.ru у «Строительного
   управления» — это адреса ХОСТЕРОВ, снятые обходчиком с сайта. Компании
   они не принадлежат, письма туда уходят в поддержку хостинга.

    python snyat_erk_i_hostery.py            # показать
    python snyat_erk_i_hostery.py primenit   # сделать
"""
import sqlite3
import sys
import time

sys.path.insert(0, r"C:\sender")
from sender.ne_nash import НеНаш                              # noqa: E402

ДЕЛАТЬ = "primenit" in sys.argv[1:]
БАЗА = r"C:\sender\sender.db"
КОНКУРЕНТ = "6679054575"
ХОСТЕРЫ = ("support@sweb.ru", "info@timeweb.ru")

c = sqlite3.connect(БАЗА, timeout=60)
c.row_factory = sqlite3.Row

print("=== конкурент ===")
for r in c.execute("SELECT id, company_name, email FROM recipients WHERE inn=?",
                   (КОНКУРЕНТ,)):
    print("   %s | %s" % (r["company_name"], r["email"]))
    for cr in c.execute("SELECT id, status, substr(subject,1,50) s FROM "
                        "confirm_reviews WHERE recipient_id=?", (r["id"],)):
        print("      карточка #%s %s | %s" % (cr["id"], cr["status"], cr["s"]))

print("")
print("=== адреса хостеров ===")
for а in ХОСТЕРЫ:
    for r in c.execute("SELECT id, inn, company_name, email FROM recipients "
                       " WHERE email=?", (а,)):
        print("   %s → %s (ИНН %s)" % (а, str(r["company_name"])[:50], r["inn"]))
        for cr in c.execute("SELECT id, status, substr(subject,1,44) s FROM "
                            "confirm_reviews WHERE recipient_id=?", (r["id"],)):
            print("      карточка #%s %s | %s" % (cr["id"], cr["status"], cr["s"]))

if not ДЕЛАТЬ:
    print("\nвхолостую. Сделать — primenit")
    raise SystemExit(0)

сейчас = time.strftime("%Y-%m-%dT%H:%M:%S")
реестр = НеНаш(БАЗА, зеркало=r"C:\sender\enrich.db")
реестр.записать(КОНКУРЕНТ, "конкурент: сам производит поршневые компрессоры "
                           "и запчасти к ним (erk-ekb.ru, ответ 26.08)",
                "владелец 26.08")
print("в реестр «не наш адресат»: %s" % КОНКУРЕНТ)
for r in c.execute("SELECT id FROM recipients WHERE inn=?", (КОНКУРЕНТ,)):
    c.execute("UPDATE confirm_reviews SET status='stoplist', "
              "reason='конкурент: сам делает компрессоры', decided_at=?, "
              "decided_by='владелец 26.08', updated_at=? "
              " WHERE recipient_id=? AND status IN ('pending','approved','edited')",
              (сейчас, сейчас, r["id"]))

# Адрес хостера компании не принадлежит: гасим письма и чистим контакт,
# чтобы обогащение не подставило его снова тем же путём.
for а in ХОСТЕРЫ:
    for r in c.execute("SELECT id FROM recipients WHERE email=?", (а,)).fetchall():
        c.execute("UPDATE confirm_reviews SET status='skipped', "
                  "reason='адрес хостера, компании не принадлежит', "
                  "decided_at=?, updated_at=? WHERE recipient_id=? "
                  "  AND status IN ('pending','approved','edited')",
                  (сейчас, сейчас, r["id"]))
        c.execute("UPDATE messages SET status='skipped', "
                  "last_error='адрес хостера, компании не принадлежит', "
                  "updated_at=? WHERE recipient_id=? "
                  "  AND status NOT IN ('sent','sending')", (сейчас, r["id"]))
    c.execute("INSERT OR IGNORE INTO suppression (scope, value, reason, source, "
              "created_at) VALUES ('email', ?, 'competitor', 'адрес хостера', ?)",
              (а, сейчас))
c.commit()
c.close()
print("готово")
