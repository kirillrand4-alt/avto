# -*- coding: utf-8 -*-
"""Приговорённые адреса, не доехавшие до стоп-листа и до обогащения.

Правило репозитория: мёртвый адрес обязан выпадать из работы ОДИН раз и
навсегда. Приговором считаются только «нет ящика» и «нет MX».

    python mertvye_ne_v_stopliste.py            # посчитать
    python mertvye_ne_v_stopliste.py primenit   # дописать в стоп-лист
"""
import sqlite3
import sys
import time

ДЕЛАТЬ = "primenit" in sys.argv[1:]
БАЗА = r"C:\sender\sender.db"
ОБОГ = r"C:\sender\enrich.db"

c = sqlite3.connect(БАЗА, timeout=60)
c.row_factory = sqlite3.Row

приговор = c.execute(
    "SELECT COUNT(*) FROM addr_probe WHERE verdict IN ('нет ящика','нет MX')"
).fetchone()[0]
нет_в_стопе = c.execute(
    "SELECT COUNT(*) FROM addr_probe p LEFT JOIN suppression s "
    "  ON s.value = p.email AND s.scope='email' "
    " WHERE p.verdict IN ('нет ящика','нет MX') AND s.value IS NULL"
).fetchone()[0]
print("приговоров «мёртв» в addr_probe: %d" % приговор)
print("из них НЕТ в стоп-листе: %d" % нет_в_стопе)

в_очереди = c.execute(
    "SELECT COUNT(*) FROM addr_probe p "
    "  JOIN recipients r ON r.email=p.email "
    "  JOIN confirm_reviews cr ON cr.recipient_id=r.id "
    " WHERE p.verdict IN ('нет ящика','нет MX') "
    "   AND cr.status IN ('pending','approved','edited')"
).fetchone()[0]
print("и при этом письмо им ещё ждёт в очереди: %d" % в_очереди)

try:
    o = sqlite3.connect(ОБОГ, timeout=60)
    ряды = {r[0] for r in o.execute(
        "SELECT email FROM emails WHERE probe_verdict IN ('нет ящика','нет MX')")}
    o.close()
    приг = {r[0] for r in c.execute(
        "SELECT email FROM addr_probe WHERE verdict IN ('нет ящика','нет MX')")}
    print("нет вердикта в обогащении: %d" % len(приг - ряды))
except Exception as ex:                                       # noqa: BLE001
    print("обогащение не прочлось: %s" % str(ex)[:90])

if not ДЕЛАТЬ:
    print("\nвхолостую. Дописать в стоп-лист — primenit")
    raise SystemExit(0)

# Пишем ТЕМ ЖЕ путём, что и приём вердиктов: store.suppression_add
# идемпотентен и знает про правило «unsubscribe не понижаем». Сырым INSERT
# легко разойтись с боевым поведением.
import sys as _s
_s.path.insert(0, r"C:\sender")
from sender.config import Config                              # noqa: E402
from sender.dtos import SuppressionIn                         # noqa: E402
from sender.store import Store                                # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(БАЗА)
ряды = c.execute(
    "SELECT p.email, p.verdict, p.answer FROM addr_probe p "
    "  LEFT JOIN suppression s ON s.value = p.email AND s.scope='email' "
    " WHERE p.verdict IN ('нет ящика','нет MX') AND s.value IS NULL").fetchall()
добавлено = сбоев = 0
for r in ряды:
    try:
        store.suppression_add(SuppressionIn(
            scope="email", value=r["email"], reason="bounce_hard",
            source="проба (добор 26.08)"))
        добавлено += 1
    except Exception as ex:                                   # noqa: BLE001
        сбоев += 1
        if сбоев <= 3:
            print("   сбой на %s: %s" % (r["email"], str(ex)[:90]))
print("\nдописано в стоп-лист: %d, сбоев: %d" % (добавлено, сбоев))

# Обогащение: его читает отбор кандидатов, и без вердикта мёртвый адрес
# снова всплывёт в новой партии.
try:
    from sender.probe_enrich import записать as _в_обогащение  # noqa: E402
    путь = cfg.get("service.enrich_db", None) or ОБОГ
    пачка = [{"email": r["email"], "verdict": r["verdict"],
              "answer": r["answer"]} for r in ряды]
    итог = _в_обогащение(путь, пачка)
    print("в обогащение: %s" % итог)
except Exception as ex:                                       # noqa: BLE001
    print("обогащение не приняло: %s" % str(ex)[:120])
c.close()
