# -*- coding: utf-8 -*-
"""Сверка приговоров: мёртвый адрес обязан выпасть из работы целиком.

Правило репозитория: вердикт «нет ящика»/«нет MX» живёт в трёх местах —
кэш панели (addr_probe), стоп-лист (suppression), обогащение (emails). Если
хоть одна запись не легла, адрес возвращается в отбор следующим прогоном.
26.08 так разошлись 5120 приговоров: писать в стоп-лист мешал чужой поток,
а первый же сбой проглатывался молча.

Правки в probe_sync и probe_enrich это чинят на будущее, но сверка нужна и
дальше: сбой всё равно возможен, и он не должен стоить компании. Прогон
идемпотентный, гоняем по расписанию.

    python sverka_prigovorov.py            # посчитать
    python sverka_prigovorov.py primenit   # довести до конца
"""
import os
import sqlite3
import sys
import time

sys.path.insert(0, r"C:\sender")

ДЕЛАТЬ = "primenit" in sys.argv[1:]
БАЗА = r"C:\sender\sender.db"
ОБОГ = r"C:\sender\enrich.db"
ПРИГОВОР = ("нет ящика", "нет MX")

c = sqlite3.connect(БАЗА, timeout=60)
c.row_factory = sqlite3.Row
нет_в_стопе = c.execute(
    "SELECT p.email, p.verdict, p.answer FROM addr_probe p "
    "  LEFT JOIN suppression s ON s.value=p.email AND s.scope='email' "
    " WHERE p.verdict IN (?,?) AND s.value IS NULL", ПРИГОВОР).fetchall()
в_очереди = c.execute(
    "SELECT cr.id, cr.message_id, r.email, p.verdict FROM confirm_reviews cr "
    "  JOIN recipients r ON r.id=cr.recipient_id "
    "  JOIN addr_probe p ON p.email=r.email "
    " WHERE p.verdict IN (?,?) "
    "   AND cr.status IN ('pending','approved','edited')", ПРИГОВОР).fetchall()
все_приговоры = [dict(r) for r in c.execute(
    "SELECT email, verdict, answer FROM addr_probe WHERE verdict IN (?,?)",
    ПРИГОВОР)]
print("приговоров всего: %d | нет в стоп-листе: %d | писем в очереди: %d"
      % (len(все_приговоры), len(нет_в_стопе), len(в_очереди)))

if not ДЕЛАТЬ:
    print("\nвхолостую. Довести — primenit")
    c.close()
    raise SystemExit(0)

from sender.dtos import SuppressionIn                         # noqa: E402
from sender.store import Store                                # noqa: E402

store = Store(БАЗА)
легло = сбоев = 0
for r in нет_в_стопе:
    try:
        store.suppression_add(SuppressionIn(
            scope="email", value=r["email"], reason="bounce_hard",
            source="сверка приговоров"))
        легло += 1
    except Exception:                                         # noqa: BLE001
        сбоев += 1
print("в стоп-лист: %d, сбоев: %d" % (легло, сбоев))

сейчас = time.strftime("%Y-%m-%dT%H:%M:%S")
снято = 0
for r in в_очереди:
    причина = "адрес недоставим: %s (сверка приговоров)" % r["verdict"]
    c.execute("UPDATE confirm_reviews SET status='skipped', reason=?, "
              "decided_at=?, decided_by='сверка приговоров', updated_at=? "
              " WHERE id=? AND status IN ('pending','approved','edited')",
              (причина, сейчас, сейчас, r["id"]))
    if r["message_id"]:
        c.execute("UPDATE messages SET status='skipped', last_error=?, "
                  "updated_at=? WHERE id=? AND status NOT IN ('sent','sending')",
                  (причина, сейчас, r["message_id"]))
    снято += 1
c.commit()
c.close()
print("снято писем: %d" % снято)

try:
    from sender.probe_enrich import записать                  # noqa: E402
    print("в обогащение: %s" % записать(
        ОБОГ if os.path.exists(ОБОГ) else None, все_приговоры))
except Exception as ex:                                       # noqa: BLE001
    print("обогащение не приняло: %s" % str(ex)[:120])
