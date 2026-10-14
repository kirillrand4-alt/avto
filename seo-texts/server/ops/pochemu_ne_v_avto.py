# -*- coding: utf-8 -*-
"""Почему кнопка «В автоотправку» пропускает письма: те же проверки, что в
app.py bulk-to-auto (удержание карточки → _guard → гейт направлений), по всей
очереди pending. Только чтение.

    pochemu_ne_v_avto.py [kampaniya=14]
"""
import json
import re
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.company_card import CompanyCards  # noqa: E402
from sender.config import Config  # noqa: E402
from sender.confirm import ConfirmSend  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.suppression import Suppression  # noqa: E402

им = dict(а.split("=", 1) for а in sys.argv[1:] if "=" in а)
КАМП = int(им.get("kampaniya", "14"))
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cards = CompanyCards(index_path=r"C:\sender\obzvon-index.db", enrich_db_path=r"C:\sender\enrich.db")
cs = ConfirmSend(cfg, store, Suppression(store), cards=cards)
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
c.row_factory = sqlite3.Row
св, прим = Counter(), {}
for р in c.execute("SELECT id, inn, email, campaign_id, panel_json FROM confirm_reviews "
                   "WHERE status='pending' AND campaign_id=?", (КАМП,)):
    r = dict(р)
    try:
        п = json.loads(r["panel_json"] or "{}")
    except Exception:  # noqa: BLE001
        п = {}
    if (п.get("actions") or {}).get("confirm_hold"):
        к = "удержание карточки: " + ",".join(sorted(str(f.get("code")) for f in п.get("stop_flags") or []))
    else:
        bl = None
        try:
            bl = cs._guard(inn=r["inn"], email=r["email"] or "")
        except Exception as е:  # noqa: BLE001
            bl = "сбой _guard: %s" % е
        if bl:
            к = "заслон: " + re.sub(r"\d{4}-\d\d-\d\d\S*|\d+", "N", str(bl))[:70]
        else:
            dv = None
            try:
                dv = cs._division_blocked(r)
            except Exception as е:  # noqa: BLE001
                dv = "сбой: %s" % е
            к = ("направления: " + str(dv)[:70]) if dv else "ПРОХОДИТ"
    св[к] += 1
    прим.setdefault(к, "%s %s" % (r["inn"], r["email"]))
for к, n in св.most_common():
    print("%5d  %s   (напр. %s)" % (n, к, прим[к]))
print("=== ПОЧЕМУ НЕ В АВТО ===")
