# -*- coding: utf-8 -*-
"""На каких данных модель решила «никуда» по спорным карточкам."""
import io
import json
import sys

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")
from sender.ai_quota import build_ai_quota                    # noqa: E402
from sender.config import Config                             # noqa: E402
from sender.store import Store                               # noqa: E402

ИНТЕРЕСНЫЕ = ("НОВОТЕРРА", "АЛЬБАТРОС", "ФОРТУНА", "РОДНЫЕ ПРОСТОРЫ",
              "ЖИТНИЦА АЛТАЯ", "СТАРОМИХАЙЛОВСКИЙ", "МЕРКИД")

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

for з in итог.values():
    if з.get("вердикт") != "никуда":
        continue
    if not any(и in str(з.get("имя") or "").upper() for и in ИНТЕРЕСНЫЕ):
        continue
    rec = store.get_recipient(int(з["rid"]))
    if rec is None:
        continue
    req = q._request(rec)
    паспорт = ""
    try:
        паспорт = q._pasport_dlya_geyta(з["инн"]) or ""
    except Exception:                                         # noqa: BLE001
        pass
    текст = str((req.get("extra") or {}).get("site_text") or "")
    print("")
    print("=== %s (ИНН %s)" % (з.get("имя"), з.get("инн")))
    print("   вердикт: %s — %s" % (з.get("вердикт"), з.get("почему")))
    print("   ОКВЭД:   %s" % (getattr(rec, "okved", "") or "нет"))
    print("   занятие: %s" % (str(req.get("activity") or "нет")[:200]))
    print("   паспорт: %s" % (паспорт[:200] or "нет"))
    print("   сайт:    %s" % (" ".join(текст.split())[:200] or "нет"))
