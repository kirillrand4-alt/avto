# -*- coding: utf-8 -*-
"""Карточки спорных снятых: овощи для HoReCa и добыча."""
import io
import json
import re
import sys

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")
from sender.ai_quota import build_ai_quota                    # noqa: E402
from sender.config import Config                              # noqa: E402
from sender.store import Store                                # noqa: E402

СЛОВА = re.compile(r"овощ|фрукт|horeca|хорека|добыч|золот|руд|карьер|шахт|"
                   r"гок|обогатительн|щебен|песк|минерал|уголь", re.I)

итог = {}
for с in io.open(r"C:\sender\_ops\predprosev-meyer.jsonl",
                 encoding="utf-8", errors="replace"):
    с = с.strip()
    if not с:
        continue
    try:
        з = json.loads(с)
    except Exception:                                         # noqa: BLE001
        continue
    if з.get("инн"):
        итог[з["инн"]] = з

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)

найдено = 0
for з in итог.values():
    if з.get("вердикт") != "никуда":
        continue
    if not СЛОВА.search(str(з.get("почему") or "") + " " + str(з.get("имя") or "")):
        continue
    rec = store.get_recipient(int(з["rid"]))
    if rec is None:
        continue
    try:
        паспорт = q._pasport_dlya_geyta(з["инн"]) or ""
    except Exception:                                         # noqa: BLE001
        паспорт = ""
    найдено += 1
    print("")
    print("=== %s (ИНН %s)" % (str(з.get("имя"))[:60], з.get("инн")))
    print("   вердикт: %s" % str(з.get("почему"))[:150])
    print("   ОКВЭД:   %s" % (getattr(rec, "okved", "") or "нет"))
    print("   паспорт: %s" % (" ".join(паспорт.split())[:340] or "нет"))
    if найдено >= 14:
        break
print("")
print("всего таких снятых: %d (показано %d)"
      % (sum(1 for з in итог.values() if з.get("вердикт") == "никуда"
             and СЛОВА.search(str(з.get("почему") or "") + " "
                              + str(з.get("имя") or ""))), найдено))
