# -*- coding: utf-8 -*-
"""Адреса очереди без вердикта пробы: показать и отдать работнику срочно.

Владелец 26.08 увидел в карточке «адрес не проверялся» и спросил почему.
Здесь видно и сколько таких, и жив ли круг публикации.

    python dotolkat_probu.py           # показать
    python dotolkat_probu.py --katit   # отдать работнику
"""
import io
import os
import re
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")

КАТИТЬ = "--katit" in sys.argv

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
без = [r["email"] for r in c.execute(
    "SELECT DISTINCT r.email FROM confirm_reviews cr "
    "  JOIN recipients r ON r.id=cr.recipient_id "
    "  LEFT JOIN addr_probe p ON p.email=r.email "
    " WHERE cr.status IN ('pending','approved','edited') AND p.email IS NULL "
    "   AND r.email IS NOT NULL AND r.email <> ''")]
c.close()
print("адресов очереди без вердикта: %d" % len(без))
for а in без[:10]:
    print("   %s" % а)

print("")
print("=== следы круга публикации в логах панели ===")
найдено = 0
for имя in ("panel_out.log", "panel_err.log"):
    п = os.path.join(r"C:\sender\_ops", имя)
    if not os.path.exists(п):
        continue
    строки = io.open(п, encoding="utf-8", errors="replace").read().splitlines()
    свои = [с for с in строки if re.search(r"probe_sync|проба|addr_probe", с, re.I)]
    print("   %s: строк про пробу %d" % (имя, len(свои)))
    for с in свои[-5:]:
        print("      " + с[:160])
    найдено += len(свои)
if not найдено:
    print("   в логах панели про пробу тихо")

if not КАТИТЬ:
    print("\nсухой прогон. Отдать работнику — --katit")
    raise SystemExit(0)

from sender.addr_probe import build_addr_probe                # noqa: E402
from sender.config import Config                              # noqa: E402
from sender.probe_sync import build_probe_sync                # noqa: E402
from sender.store import Store                                # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
# build_addr_probe отдаёт ФОНОВЫЙ ЦИКЛ, а ProbeSync ждёт саму пробу с
# методом cached: у цикла она лежит в поле probe_.
цикл = build_addr_probe(store, cfg)
probe = getattr(цикл, "probe_", цикл)
sync = build_probe_sync(store, probe, cfg)
итог = sync.срочно(без)
print("\nотдано работнику: %s" % итог)
