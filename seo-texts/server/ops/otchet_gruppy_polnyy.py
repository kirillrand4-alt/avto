# -*- coding: utf-8 -*-
"""Полный отчёт владельцу 14.10 по всем компаниям, загруженным в группы
«Россия 9000» и «Белорусь 1000»: один итоговый статус на компанию + детали.
Пишет _ops/otchet-gruppy.csv (и копию на дроп) и печатает сводку. Только чтение.

Статус по старшинству: ответили нам > отправлено > в очереди > сбой отправки >
снято (скип) > брак генерации > не подходит > нет живого адреса > не наш/сделка >
ещё не писали (кандидат Meyer/КЦ)."""
import csv
import glob
import io
import json
import shutil
import sqlite3
import sys
from collections import Counter, defaultdict

sys.path.insert(0, r"C:\sender")
from sender.sdelki_napr import blok  # noqa: E402

ГР = ("Россия 9000", "Белорусь 1000")
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
e = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
o = sqlite3.connect(r"C:\sender\obzvon-index.db", timeout=60)
кампания = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}


def напр_камп(кид):
    н = str(кампания.get(кид, "")).lower()
    return "Meyer" if ("meyer" in н or "мейер" in н) else "КЦ"


группа, адреса, рид = {}, defaultdict(set), defaultdict(set)
for rid_, inn, em, ex in c.execute("SELECT id, inn, email, extra_json FROM recipients WHERE inn IS NOT NULL"):
    inn = str(inn)
    if em and "@" in str(em):
        адреса[inn].add(str(em).strip().lower())
    for г in ГР:
        if г in str(ex or ""):
            группа.setdefault(inn, г)
            рид[inn].add(rid_)
for inn, em in e.execute("SELECT inn, email FROM emails WHERE email LIKE '%@%'"):
    адреса[str(inn)].add(str(em).strip().lower())
комп = {str(r[0]): r[1:] for r in e.execute(
    "SELECT inn, name, revenue_rub, okved, verdikt_napr, verdikt_istochnik, verdikt_rusprom FROM companies")}
метка = {str(r[0]): r[1] for r in o.execute("SELECT inn, division FROM obzvon")}
мёртвые = {str(r[0]).lower() for r in c.execute(
    "SELECT email FROM addr_probe WHERE verdict IN ('нет ящика','нет MX','no_mailbox','no_mx','dead')")}
лиды = defaultdict(list)
for inn, st, kind in c.execute("SELECT inn, status, reply_kind FROM leads WHERE inn IS NOT NULL"):
    лиды[str(inn)].append("%s/%s" % (kind or "?", st or "?"))
try:
    from sender.ne_nash import build_ne_nash
    не_наш = set(build_ne_nash().набор(None) or [])
except Exception:  # noqa: BLE001
    не_наш = set()

# письма: по получателям ГРУППЫ и отдельно — той же компании из других кампаний
письма = defaultdict(list)
раньше = defaultdict(Counter)
for rid_, inn, кид, st, ts in c.execute(
        "SELECT m.recipient_id, r.inn, m.campaign_id, m.status, COALESCE(m.sent_at, m.updated_at, m.created_at) "
        "FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE r.inn IS NOT NULL"):
    inn = str(inn)
    if inn not in группа:
        continue
    if rid_ in рид[inn]:
        письма[inn].append((st, напр_камп(кид), str(ts or "")[:10], кампания.get(кид, кид)))
    elif st == "sent":
        раньше[inn][напр_камп(кид)] += 1

# журналы генерации: последний итог по ИНН
ген = {}
for ф in sorted(glob.glob(r"C:\sender\_ops\gen-*.jsonl")):
    with io.open(ф, encoding="utf-8", errors="replace") as f:
        for стр in f:
            if '"итог"' not in стр:
                continue
            try:
                з = json.loads(стр)
            except ValueError:
                continue
            inn = str(з.get("inn") or "")
            if inn in группа:
                ген[inn] = (bool(з.get("ок")), "; ".join(map(str, з.get("брак") or []))[:200],
                            з.get("направление"), з.get("день"))


def причина_брака(т):
    т = т.lower()
    if "не покупатель" in т:
        return "брак: не покупатель (линза)"
    if "i can" in т or "нет json" in т or "прогон упал" in т:
        return "брак: сбой/отказ модели"
    if "линза" in т or "технолог" in т or "скептик" in т:
        return "брак: техническая линза"
    if "очередь" in т or "message_id" in т:
        return "брак: не встало в очередь"
    return "брак: гейт текста"


ЖИВ = ("pending_review", "approved", "scheduled", "sending")
строки, свод = [], Counter()
for inn, г in группа.items():
    name, выр, окв, napr, ист, rus = (комп.get(inn) or (None,) * 6)
    п = письма.get(inn, [])
    ст = {x[0] for x in п}
    живые_адр = [a for a in адреса.get(inn, ()) if a not in мёртвые]
    дет = ""
    if лиды.get(inn):
        статус, дет = "ответили нам", ", ".join(лиды[inn][:3])
    elif "sent" in ст:
        x = max((x for x in п if x[0] == "sent"), key=lambda x: x[2])
        статус, дет = "отправлено %s" % x[1], "%s, %s" % (x[2], x[3])
    elif ст & set(ЖИВ):
        x = next(x for x in п if x[0] in ЖИВ)
        статус, дет = "в очереди %s" % x[1], "%s, %s" % (x[0], x[3])
    elif "failed" in ст:
        статус = "сбой отправки"
    elif ст & {"skipped", "rejected", "cancelled", "suppressed"}:
        статус = "снято с очереди"
        дет = ",".join(sorted(ст))
    elif inn in ген and not ген[inn][0]:
        статус, дет = причина_брака(ген[inn][1]), ген[inn][1]
    elif napr in ("никуда", "не мейер", "не кц") or (not napr and rus == "не покупатель"):
        статус, дет = "не подходит никому", "вердикт %s (%s)" % (napr or rus, ист or "")
    elif not живые_адр:
        статус = "нет живого адреса"
    elif inn in не_наш:
        статус = "не наш / клиент"
    elif napr == "кц" and blok(c, inn, "kc"):
        статус = "сделка КЦ в работе"
    else:
        кто = ("Meyer+КЦ" if napr == "оба" else "КЦ" if napr == "кц"
               else "Meyer" if napr == "мейер" else "Meyer (без вердикта)")
        статус = "ещё не писали: " + кто
    свод[(г, статус)] += 1
    строки.append([г, inn, name or "", round(float(выр or 0) / 1e6, 1), окв or "", napr or "",
                   метка.get(inn) or "", статус, дет,
                   "; ".join("%s %d" % kv for kv in раньше[inn].items()),
                   len(живые_адр), "; ".join(sorted(живые_адр)[:3])])
строки.sort(key=lambda r: (r[0], r[7], -r[3]))
путь = r"C:\sender\_ops\otchet-gruppy.csv"
with io.open(путь, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f, delimiter=";")
    w.writerow(["группа", "ИНН", "компания", "выручка, млн", "ОКВЭД", "вердикт направления", "метка обзвона",
                "статус", "детали", "писали раньше (др. кампании, отправлено)", "живых адресов", "адреса"])
    w.writerows(строки)
shutil.copy2(путь, r"C:\seostat\drop\drop-storage\ops_otchet-gruppy.csv")
for г in ГР:
    print("== %s: компаний %d" % (г, sum(v for k, v in свод.items() if k[0] == г)))
    for (гг, s), n in sorted(свод.items(), key=lambda kv: -kv[1]):
        if гг == г:
            print("   %-40s %6d" % (s, n))
print("=== ОТЧЁТ ПО ГРУППАМ ===")
