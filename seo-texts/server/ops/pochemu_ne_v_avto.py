# -*- coding: utf-8 -*-
"""Почему карточки на подтверждении не идут «В автоотправку»: те же проверки, что у кнопки
(стоп-флаг, _guard, гейт направлений). Только чтение."""
import json, sqlite3, sys
from collections import Counter
sys.path.insert(0, r"C:\sender")
from sender.config import Config
from sender.store import Store
from sender.confirm import ConfirmSend
from sender.suppression import Suppression
cfg = Config.load(r"C:\sender\sender.yaml")
st = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = ConfirmSend(cfg, st, Suppression(st))
сч = Counter()
for r in cs.pending(limit=100000):
    if (r.get("kind") or "outbound") == "reply": continue
    p = r.get("panel") if isinstance(r.get("panel"), dict) else {}
    if ((p or {}).get("actions") or {}).get("confirm_hold"): why = "стоп-флаг"
    else:
        why = cs._guard(inn=r.get("inn"), email=r.get("email")) or ""
        if not why:
            d = cs._division_blocked(r)
            why = ("гейт направлений: %s" % d) if d else "проходит"
    сч[str(why)[:110]] += 1
    print("#%s %s %s — %s" % (r.get("id"), r.get("email"), r.get("inn"), str(why)[:110]))
print(dict(сч))
