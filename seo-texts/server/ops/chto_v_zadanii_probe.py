# -*- coding: utf-8 -*-
"""Что лежит в задании работнику: сколько адресов уже проверено и сколько доменов.

Работник (probe_worker.py) берёт задание целиком, но за проход проверяет не
больше --per-domain адресов одного домена (по умолчанию 3) и пропускает те,
что уже сделал. Значит скорость упирается не в лимит, а в РАЗНООБРАЗИЕ
ДОМЕНОВ в задании.
"""
import json, sys
from collections import Counter
sys.path.insert(0, r"C:\sender")
from sender.addr_probe import build_addr_probe                  # noqa: E402
from sender.config import Config                                # noqa: E402
from sender.probe_sync import build_probe_sync, ЗАДАЧА          # noqa: E402
from sender.store import Store                                  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
sync = build_probe_sync(store, build_addr_probe(store, cfg).probe_, cfg)
try:
    сырое = sync._дроп("GET", "probe-zadanie.json")
    адреса = json.loads(сырое.decode("utf-8", "replace"))
except Exception as ex:                                         # noqa: BLE001
    print("задание не забралось: %s: %s" % (type(ex).__name__, str(ex)[:120]))
    raise SystemExit(1)
if isinstance(адреса, dict):
    адреса = адреса.get("emails") or []
адреса = [str(a).strip().lower() for a in адреса if a and "@" in str(a)]

with store._lock:
    есть = {str(r["email"] or "").lower() for r in
            store._conn.execute("SELECT email FROM addr_probe")}
новые = [a for a in адреса if a not in есть]
домены = Counter(a.rsplit("@", 1)[-1] for a in новые)
print("--- домены среди НЕПРОВЕРЕННЫХ в задании ---")
for д, n in домены.most_common(12):
    print("   %-28s %4d" % (д, n))
print("")
print("=" * 74)
print("=== ЗАДАНИЕ РАБОТНИКУ ===")
print("адресов в задании: %d" % len(адреса))
print("из них уже с вердиктом: %d" % (len(адреса) - len(новые)))
print("НОВЫХ для работника: %d, разных доменов среди них: %d"
      % (len(новые), len(домены)))
print("потолок одного прохода при --per-domain=3: %d адресов"
      % min(len(новые), 3 * len(домены)))
