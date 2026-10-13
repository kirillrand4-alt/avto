# -*- coding: utf-8 -*-
"""Лиды по кампаниям и статусам + имя/направление кампании."""
import sqlite3
from collections import Counter, defaultdict
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
по = defaultdict(Counter)
for р in c.execute("SELECT campaign_id, status FROM leads"):
    по[р["campaign_id"]][р["status"]] += 1
for р in c.execute("SELECT id, name, status, config_json FROM campaigns ORDER BY id"):
    if р["id"] in по or True:
        print("#%-3s %-40s %-9s %s | лиды %s" % (р["id"], str(р["name"])[:40], р["status"],
              str(р["config_json"] or "")[:80], dict(по.get(р["id"], {}))))
print("лиды без кампании: %s" % dict(по.get(None, {})))
print("=== ЛИДЫ ПО КАМПАНИЯМ ===")
