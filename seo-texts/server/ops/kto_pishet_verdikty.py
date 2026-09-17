# -*- coding: utf-8 -*-
"""Кто пишет вердикты, если работник мёртв: гистограмма времени записи."""
import sys
import time
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
with store._lock:
    c = store._conn
    print("--- addr_probe: когда строка записана, по дням ---")
    for р in c.execute("SELECT substr(ts,1,10) д, COUNT(*) n, "
                       "       COALESCE(source,'(пусто)') и FROM addr_probe "
                       " GROUP BY 1,3 ORDER BY 1 DESC LIMIT 14"):
        print("   %s  %-14s %6d" % (р["д"], str(р["и"])[:14], р["n"]))

    print("")
    print("--- сегодняшние записи по часам ---")
    for р in c.execute("SELECT substr(ts,1,13) ч, COUNT(*) n FROM addr_probe "
                       " WHERE ts >= date('now') GROUP BY 1 ORDER BY 1 DESC "
                       " LIMIT 10"):
        print("   %s  %6d" % (р["ч"], р["n"]))

    print("")
    print("--- за последние 20 минут ---")
    n = c.execute("SELECT COUNT(*) FROM addr_probe "
                  " WHERE ts >= datetime('now','-20 minutes')").fetchone()[0]
    print("   строк переписано: %d" % n)

    print("")
    print("--- размер базы панели ---")
    for р in c.execute("SELECT name FROM sqlite_master WHERE type='table' "
                       " ORDER BY name"):
        pass
    стр = c.execute("SELECT page_count*page_size b FROM pragma_page_count(), "
                    " pragma_page_size()").fetchone()
    print("   sender.db: %.1f МБ" % (int(стр["b"]) / 1048576.0))

# сколько строк в файле результатов на дропе
print("")
print("--- файл результатов, который качается каждый круг ---")
import urllib.request, os
база = os.environ.get("DROP_URL", "").rstrip("/")
токен = os.environ.get("DROP_TOKEN", "")
if not база or not токен:
    п = r"C:\sender\server\runner-secrets.env"
    if os.path.exists(п):
        for с in open(п, encoding="utf-8", errors="replace"):
            if с.startswith("DROP_URL="):
                база = база or с.split("=", 1)[1].strip().rstrip("/")
            if с.startswith("DROP_TOKEN="):
                токен = токен or с.split("=", 1)[1].strip()
try:
    з = urllib.request.Request("%s/probe-rezultat.jsonl" % база)
    з.add_header("X-Drop-Token", токен)
    т0 = time.time()
    with urllib.request.urlopen(з, timeout=120) as о:
        данные = о.read()
    прошло = time.time() - т0
    строки = данные.decode("utf-8", "replace").splitlines()
    адреса = set()
    import json as _j
    for с in строки:
        try:
            адреса.add(str(_j.loads(с).get("email") or "").lower())
        except Exception:                                       # noqa: BLE001
            pass
    print("   скачано %.1f МБ за %.1f с" % (len(данные) / 1048576.0, прошло))
    print("   строк: %d, уникальных адресов: %d" % (len(строки), len(адреса)))
except Exception as ex:                                         # noqa: BLE001
    print("   не скачалось: %s" % str(ex)[:120])
print("")
print("=" * 74)
print("=== КТО ПИШЕТ ВЕРДИКТЫ ===")
