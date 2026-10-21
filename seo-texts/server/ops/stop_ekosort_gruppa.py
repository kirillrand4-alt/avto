# -*- coding: utf-8 -*-
"""Группа «Алтай Эко Сорт» в стоп-лист (владелец 21.10: «АПК тоже добавь в
стоп-лист, другие связанные с экосортом тоже убрать»).

Связь ищем по доменам группы (altaiecosort.com, apkaes.com): все ИНН, у
которых есть адрес или сайт на этих доменах (enrich.emails, enrich.companies,
recipients), — и по ним же ИНН-соседей по тем же доменам. Каждому ИНН,
домену и адресу — запись Suppression (manual). Письма в работе этих ИНН —
skipped. Без --primenit — только показать."""
import sqlite3
import sys
import time

sys.path.insert(0, r"C:\sender")
ДОМЕНЫ = {"altaiecosort.com", "apkaes.com"}
ИНН = {"2222857382", "2225233713"}
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
e = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
for _ in range(3):  # расширяем: ИНН -> их домены -> другие ИНН на этих доменах
    for inn, em in list(e.execute("SELECT inn, lower(email) FROM emails")):
        дом = em.split("@")[-1]
        if str(inn) in ИНН and дом not in ("mail.ru", "yandex.ru", "gmail.com", "bk.ru", "list.ru", "inbox.ru", "ya.ru", "rambler.ru"):
            ДОМЕНЫ.add(дом)
        if дом in ДОМЕНЫ:
            ИНН.add(str(inn))
    for inn, site in e.execute("SELECT inn, site FROM companies WHERE site IS NOT NULL"):
        дом = str(site).lower().split("//")[-1].split("/")[0].replace("www.", "")
        if дом in ДОМЕНЫ:
            ИНН.add(str(inn))
    for inn, dom in c.execute("SELECT inn, lower(domain) FROM recipients WHERE inn IS NOT NULL"):
        if dom in ДОМЕНЫ:
            ИНН.add(str(inn))
имена = {str(r[0]): r[1] for r in e.execute("SELECT inn, name FROM companies WHERE inn IN (%s)" % ",".join("?" * len(ИНН)), list(ИНН))}
адреса = sorted({str(r[0]).lower() for r in c.execute("SELECT email FROM recipients WHERE inn IN (%s)" % ",".join("?" * len(ИНН)), list(ИНН))})
print("ИНН группы:", {i: имена.get(i) for i in sorted(ИНН)})
print("домены:", sorted(ДОМЕНЫ))
print("адреса в панели:", адреса)
в_работе = c.execute("SELECT m.id, m.status FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE r.inn IN (%s) "
                     "AND m.status IN ('pending_review','scheduled','approved')" % ",".join("?" * len(ИНН)), list(ИНН)).fetchall()
print("писем в работе:", в_работе)
if "--primenit" not in sys.argv:
    print("СУХОЙ ПРОГОН. Применить — --primenit")
    sys.exit()
from sender.config import Config            # noqa: E402
from sender.store import Store              # noqa: E402
from sender.suppression import Suppression  # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
s = Suppression(Store(cfg.get("service.db_path", r"C:\sender\sender.db")))
ИСТ = "владелец 21.10: группа Алтай Эко Сорт"
print("ИНН:", [(i, s.add_inn(i, "manual", source=ИСТ)) for i in sorted(ИНН)])
print("домены:", [(d, s.add_domain(d, "manual", source=ИСТ)) for d in sorted(ДОМЕНЫ)])
print("адреса:", [(a, s.add_email(a, "manual", source=ИСТ)) for a in адреса])
т = time.strftime("%Y-%m-%dT%H:%M:%S")
with c:
    for mid, _st in в_работе:
        c.execute("UPDATE messages SET status='skipped', last_error=?, updated_at=? WHERE id=?", (ИСТ, т, mid))
        c.execute("UPDATE confirm_reviews SET status='skipped', updated_at=? WHERE message_id=? AND status IN ('pending','approved')", (т, mid))
print("снято писем:", len(в_работе))
