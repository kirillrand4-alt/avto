# -*- coding: utf-8 -*-
"""Ящики конфига по направлениям + сколько компаний с вердиктом КЦ в базе «наш или нет»."""
import sqlite3
import sys
from collections import Counter
sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
св = Counter()
for m in cfg.mailboxes():
    св[str(getattr(m, "division", "") or "?")] += 1
print("ящики по направлениям:", dict(св))
e = sqlite3.connect(r"C:\sender\enrich.db", timeout=30)
print("вердикт направления:", dict(e.execute("SELECT coalesce(verdikt_napr,'нет'), count(*) FROM companies GROUP BY 1").fetchall()))
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
print("кампании КЦ:", c.execute("SELECT id, name, status FROM campaigns WHERE name LIKE '%КЦ%' OR name LIKE '%омпресс%' OR id IN (1,5,6,9,10)").fetchall())
print("=== ЯЩИКИ ПО НАПРАВЛЕНИЯМ ===")
