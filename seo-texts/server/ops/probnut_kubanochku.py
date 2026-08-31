# -*- coding: utf-8 -*-
"""Срочная проба двух адресов «Кубаночки»: как просили и как, вероятно, надо."""
import json
import sys
import time

sys.path.insert(0, r"C:\sender")
from sender.addr_probe import build_addr_probe                # noqa: E402
from sender.config import Config                              # noqa: E402
from sender.probe_sync import build_probe_sync                # noqa: E402
from sender.store import Store                                # noqa: E402

АДРЕСА = ["nfo@kubanochka.ru", "info@kubanochka.ru"]
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
проба = getattr(build_addr_probe(store, cfg), "probe_", None)
цикл = build_probe_sync(store, проба, cfg)
итог = цикл.срочно(АДРЕСА)
print("срочная проба: %s" % json.dumps(итог, ensure_ascii=False))
print("\nждём вердикты…")
for круг in range(10):
    time.sleep(20)
    готово = {}
    for а in АДРЕСА:
        з = проба.cached(а)
        if з:
            готово[а] = (з.get("verdict"), str(з.get("answer") or "")[:60])
    if len(готово) == len(АДРЕСА):
        break
    # подтягиваем вердикты с дропа
    try:
        цикл.забрать([])
    except Exception as e:                                    # noqa: BLE001
        print("   забрать: %s" % str(e)[:80])
print("\n=== ВЕРДИКТЫ ===")
for а in АДРЕСА:
    з = проба.cached(а)
    print("   %-24s %s" % (а, ("%s — %s" % (з.get("verdict"),
                                            str(з.get("answer") or "")[:70]))
                           if з else "вердикта пока нет"))
mx = None
try:
    mx = проба.mx_for("kubanochka.ru")
except Exception as e:                                        # noqa: BLE001
    print("   mx_for упал: %s" % str(e)[:80])
print("\nMX домена kubanochka.ru: %s" % mx)
