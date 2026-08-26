# -*- coding: utf-8 -*-
"""Снять двух бесспорных конкурентов, не дожидаясь общего прогона.

«СТК» — «официальный дистрибьютор винтовых компрессоров, генераторов газов,
рефрижераторных и адсорбционных осушителей»; «Спецдеталь» — «запчасти,
узлы, комплектующие и теплообменное оборудование для центробежных и
винтовых компрессоров». Оба продают ровно то, что продаём мы.

    python snyat_dvuh_konkurentov.py            # показать
    python snyat_dvuh_konkurentov.py primenit   # снять
"""
import sqlite3
import sys
import time

sys.path.insert(0, r"C:\sender")
from sender.ne_nash import НеНаш                              # noqa: E402

ДЕЛАТЬ = "primenit" in sys.argv[1:]
БАЗА = r"C:\sender\sender.db"
КТО = {
    "5402047696": "конкурент: официальный дистрибьютор винтовых компрессоров, "
                  "генераторов газов и осушителей",
    "1660191201": "конкурент: запчасти, узлы и теплообменное оборудование для "
                  "центробежных и винтовых компрессоров",
}

c = sqlite3.connect(БАЗА, timeout=60)
c.row_factory = sqlite3.Row
цели = []
for инн, причина in КТО.items():
    for r in c.execute("SELECT id, company_name, email FROM recipients "
                       " WHERE inn=?", (инн,)):
        карточки = c.execute(
            "SELECT id, status, message_id, substr(subject,1,52) s "
            "  FROM confirm_reviews WHERE recipient_id=? "
            "   AND status IN ('pending','approved','edited')",
            (r["id"],)).fetchall()
        print("%s (ИНН %s, %s): карточек в работе %d"
              % (r["company_name"], инн, r["email"], len(карточки)))
        for cr in карточки:
            print("   #%-6s %-9s %s" % (cr["id"], cr["status"], cr["s"]))
        цели.append((инн, причина, r["id"], карточки))

if not ДЕЛАТЬ:
    print("\nвхолостую. Снять — primenit")
    raise SystemExit(0)

реестр = НеНаш(БАЗА, зеркало=r"C:\sender\enrich.db")
сейчас = time.strftime("%Y-%m-%dT%H:%M:%S")
снято = 0
for инн, причина, rid, карточки in цели:
    реестр.записать(инн, причина, "владелец 26.08")
    for cr in карточки:
        c.execute("UPDATE confirm_reviews SET status='stoplist', reason=?, "
                  "decided_at=?, decided_by='владелец 26.08', updated_at=? "
                  " WHERE id=? AND status IN ('pending','approved','edited')",
                  (причина, сейчас, сейчас, cr["id"]))
        if cr["message_id"]:
            c.execute("UPDATE messages SET status='skipped', last_error=?, "
                      "updated_at=? WHERE id=? "
                      "  AND status NOT IN ('sent','sending')",
                      (причина, сейчас, cr["message_id"]))
        снято += 1
c.commit()
c.close()
print("\nв реестр: %d компаний, снято писем: %d" % (len(цели), снято))
