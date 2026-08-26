# -*- coding: utf-8 -*-
"""Сбросить кэш гейта тем, кого он судил ДО правила про конкурента.

Гейт кэширует вердикты по ИНН: компания, признанная покупателем вчера,
сегодня в гейт уже не попадёт и нового правила не увидит. Сбрасываем кэш
точечно — только тем, у кого в паспорте сайта вообще упомянуто НАШЕ
оборудование: остальным новое правило ничего не меняет, а пересуд стоит
денег.

    python sbrosit_kesh_geyta.py            # посчитать
    python sbrosit_kesh_geyta.py primenit   # сбросить
"""
import re
import sqlite3
import sys
import time

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")
from sender.ai_quota import build_ai_quota                    # noqa: E402
from sender.config import Config                              # noqa: E402
from sender.store import Store                                # noqa: E402

ДЕЛАТЬ = "primenit" in sys.argv[1:]
ТОВАР = re.compile(
    r"компрессор|винтов\w+ блок|азотн\w+ станц|генератор\w* азота|"
    r"генератор\w* кислорода|воздуходувк|осушител\w+ воздуха|"
    r"пневмооборудован|фотосепаратор|оптическ\w+ сортировк|"
    r"рентген\w*[- ]инспекц", re.I)

cfg = Config.load(r"C:\sender\sender.yaml")
БАЗА = cfg.get("service.db_path", r"C:\sender\sender.db")
store = Store(БАЗА)
q = build_ai_quota(store, cfg)

c = sqlite3.connect(БАЗА, timeout=90)
c.execute("PRAGMA busy_timeout=90000")
c.row_factory = sqlite3.Row
кэш = c.execute("SELECT inn, verdict FROM target_verdicts "
                " WHERE verdict='покупатель'").fetchall()
print("в кэше гейта «покупатель»: %d" % len(кэш))

к_сбросу = []
for r in кэш:
    try:
        п = q._pasport_dlya_geyta(str(r["inn"])) or ""
    except Exception:                                         # noqa: BLE001
        п = ""
    if п and ТОВАР.search(п):
        к_сбросу.append(str(r["inn"]))
print("из них с нашим оборудованием в паспорте: %d" % len(к_сбросу))
for инн in к_сбросу[:10]:
    r = c.execute("SELECT company_name FROM recipients WHERE inn=? LIMIT 1",
                  (инн,)).fetchone()
    print("   %s %s" % (инн, str(r["company_name"])[:50] if r else ""))

if not ДЕЛАТЬ:
    print("\nвхолостую. Сбросить — primenit")
    raise SystemExit(0)

сброшено = 0
for i in range(0, len(к_сбросу), 300):
    кусок = к_сбросу[i:i + 300]
    зн = ",".join("?" * len(кусок))
    for попытка in range(5):
        try:
            cur = c.execute(
                "DELETE FROM target_verdicts WHERE inn IN (%s)" % зн,
                tuple(кусок))
            сброшено += cur.rowcount
            c.commit()
            break
        except sqlite3.OperationalError:
            time.sleep(2 * (попытка + 1))
c.close()
print("\nсброшено вердиктов: %d — их пересудят по новому правилу" % сброшено)
