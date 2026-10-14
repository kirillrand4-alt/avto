# -*- coding: utf-8 -*-
"""Сколько писем Meyer ещё ФИЗИЧЕСКИ можно сгенерировать (владелец 14.10).

Компания годится, если: есть живой адрес (нет приговора пробы «нет ящика/нет MX»),
ей ещё нет письма в кампаниях Meyer (pending/approved/scheduled/sending/sent),
она не «не наш» (реестр/клиент со сделкой), не отвечала нам, и вердикт базы
«наш или нет» не говорит «кц/никуда/не мейер». Считаем отдельно группы
«Россия 9000»/«Белорусь 1000» и всё обогащение; разрез — сколько полей паспорта
и есть ли ОКВЭД. Только чтение.
"""
import json
import sqlite3
import sys
from collections import Counter, defaultdict

sys.path.insert(0, r"C:\sender")
from sender.ai_quota import build_ai_quota  # noqa: E402
from sender.config import Config  # noqa: E402
from sender.store import Store  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
e = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
МЕЙЕР = [r[0] for r in c.execute("SELECT id FROM campaigns WHERE name LIKE '%Meyer%' OR name LIKE '%Мейер%'")]
с_письмом = {str(r[0]) for r in c.execute(
    "SELECT DISTINCT r.inn FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE m.campaign_id IN (%s) "
    "AND m.status IN ('pending_review','approved','scheduled','sending','sent')" % ",".join(map(str, МЕЙЕР)))}
отвечали = {str(r[0]) for r in c.execute("SELECT DISTINCT inn FROM leads WHERE inn IS NOT NULL")}
мёртвые = {str(r[0]).lower() for r in c.execute(
    "SELECT email FROM addr_probe WHERE verdict IN ('нет ящика','нет MX','no_mailbox','no_mx','dead')")} \
    if c.execute("SELECT 1 FROM sqlite_master WHERE name='addr_probe'").fetchone() else set()
try:
    sys.path.insert(0, r"C:\sender\server\ops")
    from sender.ne_nash import build_ne_nash
    не_наш = set(build_ne_nash().набор(None) or [])
except Exception:  # noqa: BLE001
    не_наш = set()
вердикт = {str(r[0]): (r[1] or "", r[2] or "") for r in e.execute(
    "SELECT inn, verdikt_napr, verdikt_rusprom FROM companies")}
окэвд = {str(r[0]): bool(r[1]) for r in e.execute("SELECT inn, okved FROM companies")}

адреса, группа = defaultdict(set), {}
for inn, em, ex in c.execute("SELECT inn, email, extra_json FROM recipients WHERE inn IS NOT NULL AND email LIKE '%@%'"):
    inn = str(inn)
    адреса[inn].add(str(em).strip().lower())
    if "Россия 9000" in str(ex):
        группа[inn] = "Россия 9000"
    elif "Белорусь 1000" in str(ex) and inn not in группа:
        группа[inn] = "Белорусь 1000"
for inn, em in e.execute("SELECT inn, email FROM emails WHERE email LIKE '%@%'"):
    адреса[str(inn)].add(str(em).strip().lower())


def корзина(inn):
    try:
        d = q._site_facts(inn) or {}
    except Exception:  # noqa: BLE001
        d = {}
    n = sum(1 for k in ("продукция", "сырьё", "оборудование_линии", "упаковка_фасовка", "масштаб", "мощности",
                        "цитата", "описание") if d.get(k))
    return "паспорт 6+" if n >= 6 else "паспорт 3-5" if n >= 3 else "паспорт 1-2" if n >= 1 else "без паспорта"


св = Counter()
for inn, ад in адреса.items():
    живые = [a for a in ад if a not in мёртвые]
    if not живые:
        св[("—", "нет живого адреса")] += 1
        continue
    if inn in с_письмом:
        св[("—", "письмо Meyer уже есть")] += 1
        continue
    if inn in не_наш:
        св[("—", "не наш / сделка")] += 1
        continue
    if inn in отвечали:
        св[("—", "отвечали нам")] += 1
        continue
    napr, rus = вердикт.get(inn, ("", ""))
    if napr in ("кц", "никуда", "не мейер") or (rus == "не покупатель" and napr not in ("мейер", "оба")):
        св[("—", "вердикт: не покупатель Meyer")] += 1
        continue
    гр = группа.get(inn, "вне групп")
    кр = корзина(inn)
    if кр == "без паспорта" and not окэвд.get(inn):
        кр = "ни паспорта, ни ОКВЭД"
    св[(гр, кр)] += 1
итого = Counter()
for (гр, кр), n in sorted(св.items()):
    print("%-16s %-24s %6d" % (гр, кр, n))
    if гр != "—":
        итого[гр] += n
print("МОЖНО ГЕНЕРИРОВАТЬ: %s" % dict(итого))
print("=== СКОЛЬКО ЕЩЁ ===")
