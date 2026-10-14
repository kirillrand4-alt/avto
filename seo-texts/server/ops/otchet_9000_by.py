# -*- coding: utf-8 -*-
"""Отчёт владельцу 14.10: по группам «Россия 9000» и «Белорусь 1000» — сколько
писем уже написано (по статусам и направлениям) и сколько ещё можно написать
(Meyer и КЦ отдельно; те же отсевы, что в skolko_eshche_mozhno). Только чтение."""
import sqlite3
import sys
from collections import Counter, defaultdict

sys.path.insert(0, r"C:\sender")
from sender.sdelki_napr import blok  # noqa: E402

c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
e = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
ГР = ("Россия 9000", "Белорусь 1000")
кампании = {r[0]: ("meyer" if ("meyer" in (r[1] or "").lower() or "мейер" in (r[1] or "").lower()) else "kc")
            for r in c.execute("SELECT id, name FROM campaigns")}
группа, адреса = {}, defaultdict(set)
for inn, em, ex in c.execute("SELECT inn, email, extra_json FROM recipients WHERE inn IS NOT NULL"):
    inn = str(inn)
    if em and "@" in str(em):
        адреса[inn].add(str(em).strip().lower())
    for г in ГР:
        if г in str(ex or "") and inn not in группа:
            группа[inn] = г
for inn, em in e.execute("SELECT inn, email FROM emails WHERE email LIKE '%@%'"):
    адреса[str(inn)].add(str(em).strip().lower())

# 1) уже написано: письма по компаниям групп, по направлению и статусу
стат = Counter()
есть_письмо = defaultdict(set)   # inn -> {направления с живым письмом}
for inn, кид, st in c.execute("SELECT r.inn, m.campaign_id, m.status FROM messages m JOIN recipients r ON r.id=m.recipient_id"):
    inn = str(inn)
    г = группа.get(inn)
    if not г:
        continue
    н = кампании.get(кид, "kc")
    стат[(г, н, st)] += 1
    if st in ("pending_review", "approved", "scheduled", "sending", "sent"):
        есть_письмо[inn].add(н)
print("УЖЕ НАПИСАНО (письма, группа / направление / статус):")
for к in sorted(стат):
    print("   %-14s %-6s %-16s %6d" % (к[0], к[1], к[2], стат[к]))
for г in ГР:
    for н in ("meyer", "kc"):
        print("   итого %s %s: отправлено %d, ждут отправки %d" % (
            г, н, sum(v for k, v in стат.items() if k[:2] == (г, н) and k[2] == "sent"),
            sum(v for k, v in стат.items() if k[:2] == (г, н) and k[2] in ("pending_review", "approved", "scheduled", "sending"))))

# 2) сколько ещё
отвечали = {str(r[0]) for r in c.execute("SELECT DISTINCT inn FROM leads WHERE inn IS NOT NULL")}
мёртвые = {str(r[0]).lower() for r in c.execute(
    "SELECT email FROM addr_probe WHERE verdict IN ('нет ящика','нет MX','no_mailbox','no_mx','dead')")}
try:
    from sender.ne_nash import build_ne_nash
    не_наш = set(build_ne_nash().набор(None) or [])
except Exception:  # noqa: BLE001
    не_наш = set()
вердикт = {str(r[0]): (r[1] or "", r[2] or "") for r in e.execute("SELECT inn, verdikt_napr, verdikt_rusprom FROM companies")}
ещё = Counter()
for inn, г in группа.items():
    ещё[(г, "компаний в группе")] += 1
    if not [a for a in адреса.get(inn, ()) if a not in мёртвые]:
        ещё[(г, "нет живого адреса")] += 1
        continue
    if inn in отвечали:
        ещё[(г, "отвечали нам")] += 1
        continue
    napr, rus = вердикт.get(inn, ("", ""))
    if napr in ("мейер", "оба") or (not napr and rus != "не покупатель"):
        if "meyer" in есть_письмо[inn]:
            ещё[(г, "Meyer: письмо уже есть")] += 1
        elif inn in не_наш or blok(c, inn, "meyer"):
            ещё[(г, "Meyer: не наш / сделка")] += 1
        else:
            ещё[(г, "Meyer: МОЖНО НАПИСАТЬ" + ("" if napr else " (без вердикта)"))] += 1
    if napr in ("кц", "оба"):
        if "kc" in есть_письмо[inn]:
            ещё[(г, "КЦ: письмо уже есть")] += 1
        elif blok(c, inn, "kc"):
            ещё[(г, "КЦ: сделка КЦ в работе")] += 1
        else:
            ещё[(г, "КЦ: МОЖНО НАПИСАТЬ")] += 1
    if napr in ("никуда", "не мейер", "не кц") or (not napr and rus == "не покупатель"):
        ещё[(г, "никому не подходит")] += 1
print("СКОЛЬКО ЕЩЁ (компании):")
for к in sorted(ещё):
    print("   %-14s %-34s %6d" % (к[0], к[1], ещё[к]))
print("=== ОТЧЁТ 9000/BY ===")
