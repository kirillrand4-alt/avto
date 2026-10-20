# -*- coding: utf-8 -*-
"""Meyer: компании, которым писали и которые НЕ ответили, — сколько у них
«следующих контактов» по лесенке (владелец 20.10). Следующий контакт — адрес
компании из обогащения (enrich.emails) или панели, которому ещё не писали,
не мёртвый по пробе, не в стоп-листе и не «не для письма». Только чтение."""
import json
import sqlite3
from collections import Counter, defaultdict

c = sqlite3.connect(r"C:\sender\sender.db")
e = sqlite3.connect(r"C:\sender\enrich.db")
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
meyer_cid = {k for k, v in кам.items() if "meyer" in str(v).lower() or "мейер" in str(v).lower()}
писали_адр = {str(r[0]).lower() for r in c.execute("SELECT email FROM send_log WHERE outcome='sent'")}
писали_адр |= {str(r[0]).lower() for r in c.execute(
    "SELECT r.email FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE m.status NOT IN ('skipped','failed')")}
ответ_инн = {str(r[0]) for r in c.execute("SELECT DISTINCT inn FROM leads WHERE inn IS NOT NULL")}
ответ_инн |= {str(r[0]) for r in c.execute(
    "SELECT DISTINCT r.inn FROM events ev JOIN recipients r ON r.id=ev.recipient_id "
    "WHERE ev.event_type IN ('reply','reply_auto') AND r.inn IS NOT NULL")}
инн_meyer = defaultdict(set)
for inn, cid, mb, em in c.execute(
        "SELECT r.inn, m.campaign_id, m.mailbox_id, lower(r.email) FROM messages m JOIN recipients r ON r.id=m.recipient_id "
        "WHERE m.status='sent' AND r.inn IS NOT NULL AND r.inn!=''"):
    if cid in meyer_cid or ("ompressor" not in str(mb) and mb):
        if cid in meyer_cid:
            инн_meyer[str(inn)].add(em)
без_ответа = [i for i in инн_meyer if i not in ответ_инн]
стоп = set()
for т in ("suppression",):
    try:
        стоп = {str(r[0]).lower() for r in c.execute("SELECT value FROM suppression")}
    except Exception:  # noqa: BLE001
        pass
проба = {str(r[0]).lower(): str(r[1] or "") for r in c.execute("SELECT email, verdict FROM addr_probe")}
for r in e.execute("SELECT lower(email), probe_verdict FROM emails WHERE probe_verdict IS NOT NULL"):
    проба.setdefault(r[0], str(r[1] or ""))
адреса = defaultdict(set)
for inn, em, role in e.execute("SELECT inn, lower(email), role FROM emails"):
    if "не для письма" in str(role or "").lower():
        continue
    адреса[str(inn)].add(em)
for inn, em in c.execute("SELECT inn, lower(email) FROM recipients WHERE inn IS NOT NULL"):
    адреса[str(inn)].add(em)
по_числу = Counter()
по_пробе = Counter()
всего_адр = 0
компаний_с = 0
for inn in без_ответа:
    след = [a for a in адреса.get(inn, ()) if a not in писали_адр and a not in стоп
            and проба.get(a, "") not in ("нет ящика", "нет MX")]
    n = len(след)
    по_числу[min(n, 5)] += 1
    if n:
        компаний_с += 1
        всего_адр += n
        лучш = min((({"есть": 0, "принимает всё": 1, "": 2, "неясно": 3, "отказ пробе": 4}.get(проба.get(a, ""), 2)) for a in след))
        по_пробе[лучш] += 1
имя = {0: "есть", 1: "принимает всё", 2: "не проверен", 3: "неясно", 4: "отказ пробе"}
print("Meyer: компаний, которым писали:", len(инн_meyer), "| ответили:", len(инн_meyer) - len(без_ответа),
      "| без ответа:", len(без_ответа))
print("из них есть следующий контакт:", компаний_с, "| следующих адресов всего:", всего_адр)
print("по числу следующих адресов (5 = 5 и больше):", {k: по_числу[k] for k in sorted(по_числу)})
print("лучший следующий адрес по пробе:", {имя[k]: v for k, v in sorted(по_пробе.items())})
