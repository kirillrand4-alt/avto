# -*- coding: utf-8 -*-
"""Белорусь 1000: сколько получателей, сколько генерировали, и строка про Беларусь в промпте одного из них."""
import io
import json
import sqlite3
import sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.ai_quota import build_ai_quota  # noqa: E402
from sender import ai_letter as al  # noqa: E402
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
ид = [р[0] for р in c.execute("SELECT id, extra_json FROM recipients WHERE extra_json LIKE '%Белорусь 1000%'")]
были = set()
for с in io.open(r"C:\sender\_ops\gen-rossiya-9000.jsonl", encoding="utf-8", errors="replace"):
    try:
        были.add(json.loads(с).get("recipient_id"))
    except Exception:  # noqa: BLE001
        pass
print("получателей в «Белорусь 1000»: %d, генерировали: %d" % (len(ид), len(были & set(ид))))
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
req = q._request(store.get_recipient(ид[0]))
for с in al._recipient_block(0, req, "meyer").splitlines():
    if "БЕЛАРУС" in с.upper():
        print("   промпт: " + с[:260])
print("=== БЕЛАРУСЬ ===")
