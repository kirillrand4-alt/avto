# -*- coding: utf-8 -*-
"""Группа компаний по домену — в стоп-лист (владелец 21.10, air-lead.ru —
«Эр Ликид»: лид пришёл с рекламы, холодные не писать «пока что»).

ИНН группы — все, у кого есть адрес или сайт на указанных доменах (enrich.emails,
enrich.companies, recipients); один круг, без расширения на чужие домены
найденных ИНН. В Suppression (manual): каждый ИНН, каждый домен, адреса панели.
Письма в работе этих ИНН — skipped. Без --primenit — показать.

    stop_gruppa.py domeny=a.ru,b.ru istochnik="..." [--primenit]"""
import sqlite3
import sys
import time

sys.path.insert(0, r"C:\sender")
арг = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
ДОМЕНЫ = {d.strip().lower() for d in арг["domeny"].split(",") if d.strip()}
ИСТ = арг.get("istochnik", "владелец: группа в стоп-лист")
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
e = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
ИНН = set()
for inn, em in e.execute("SELECT inn, lower(email) FROM emails"):
    if em.split("@")[-1] in ДОМЕНЫ and inn:
        ИНН.add(str(inn))
for inn, site in e.execute("SELECT inn, site FROM companies WHERE site IS NOT NULL"):
    if str(site).lower().split("//")[-1].split("/")[0].replace("www.", "") in ДОМЕНЫ:
        ИНН.add(str(inn))
for inn, dom in c.execute("SELECT inn, lower(domain) FROM recipients WHERE inn IS NOT NULL"):
    if dom in ДОМЕНЫ:
        ИНН.add(str(inn))
q = ",".join("?" * len(ИНН)) or "''"
имена = {str(r[0]): r[1] for r in e.execute("SELECT inn, name FROM companies WHERE inn IN (%s)" % q, list(ИНН))}
for inn, имя in c.execute("SELECT inn, company_name FROM recipients WHERE inn IN (%s)" % q, list(ИНН)):
    имена.setdefault(str(inn), имя)
адреса = sorted({str(r[0]).lower() for r in c.execute("SELECT email FROM recipients WHERE inn IN (%s)" % q, list(ИНН))}
                | {str(r[0]).lower() for r in c.execute("SELECT email FROM recipients WHERE lower(domain) IN (%s)"
                                                        % ",".join("?" * len(ДОМЕНЫ)), list(ДОМЕНЫ))})
в_работе = c.execute("SELECT m.id FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE (r.inn IN (%s) OR lower(r.domain) IN (%s)) "
                     "AND m.status IN ('pending_review','scheduled','approved')" % (q, ",".join("?" * len(ДОМЕНЫ))),
                     list(ИНН) + list(ДОМЕНЫ)).fetchall()
print("ИНН:", {i: имена.get(i) for i in sorted(ИНН)})
print("домены:", sorted(ДОМЕНЫ))
print("адреса в панели:", адреса)
print("писем в работе:", [r[0] for r in в_работе])
if "--primenit" not in sys.argv:
    print("СУХОЙ ПРОГОН. Применить — --primenit")
    sys.exit()
from sender.config import Config            # noqa: E402
from sender.store import Store              # noqa: E402
from sender.suppression import Suppression  # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
s = Suppression(Store(cfg.get("service.db_path", r"C:\sender\sender.db")))
print("ИНН:", [(i, s.add_inn(i, "manual", source=ИСТ)) for i in sorted(ИНН)])
print("домены:", [(d, s.add_domain(d, "manual", source=ИСТ)) for d in sorted(ДОМЕНЫ)])
print("адреса:", [(a, s.add_email(a, "manual", source=ИСТ)) for a in адреса])
т = time.strftime("%Y-%m-%dT%H:%M:%S")
with c:
    for (mid,) in в_работе:
        c.execute("UPDATE messages SET status='skipped', last_error=?, updated_at=? WHERE id=?", (ИСТ, т, mid))
        c.execute("UPDATE confirm_reviews SET status='skipped', updated_at=? WHERE message_id=? AND status IN ('pending','approved')", (т, mid))
print("снято писем:", len(в_работе))
