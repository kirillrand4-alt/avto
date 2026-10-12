# -*- coding: utf-8 -*-
"""Блок получателя в промпте письма (без вызова модели): prompt_kartochki.py <rid> [<rid>…]."""
import re
import sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.ai_quota import build_ai_quota  # noqa: E402
from sender import ai_letter as al  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
for rid in sys.argv[1:]:
    rec = store.get_recipient(int(rid))
    req = q._request(rec)
    print("##### %s | сегмент=%r | okved=%r | activity=%r" % (rid, req.get("segment"),
          req.get("okved"), str(req.get("activity"))[:120]))
    блок = al._recipient_block(0, req, "meyer")
    for с in блок.splitlines():
        if re.search(r"СТАНОК|НЕПИЩЕВ|Зачем|ориентир|ЧТО ОНИ ВЫПУСКАЮТ|СЫРЬЁ|кедр|рентген", с, re.I):
            print("   " + с[:420])
print("=== ПРОМПТ ===")
