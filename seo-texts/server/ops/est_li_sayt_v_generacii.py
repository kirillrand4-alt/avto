# -*- coding: utf-8 -*-
"""Видел ли генератор текст сайта, когда писал письмо.

Если в карточке лежит только одна строка «чем занимается», то всё, что в
письме сказано про цеха и процессы, модель достроила сама. Если бы рядом
лежал текст сайта, достраивать было бы не нужно.
"""
import json
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
with store._lock:
    ряд = store._conn.execute(
        "SELECT id, panel_json FROM confirm_reviews WHERE campaign_id=10"
    ).fetchall()

свод = Counter()
длины = []
пример = {}
for cid, pj in ряд:
    try:
        p = json.loads(pj or "{}")
    except Exception:                                            # noqa: BLE001
        continue
    c = p.get("company") if isinstance(p.get("company"), dict) else {}
    факты = p.get("site_facts") or c.get("site_facts") or {}
    kb = p.get("kb") or {}
    активность = (c.get("activity") or "").strip()
    if факты:
        свод["текст/факты сайта в карточке ЕСТЬ"] += 1
        пример.setdefault("есть", (cid, str(факты)[:160]))
    elif активность:
        свод["только одна строка «чем занимается»"] += 1
        длины.append(len(активность))
        пример.setdefault("строка", (cid, активность[:120]))
    else:
        свод["ни того, ни другого"] += 1
    свод["+ справочник наших брендов (kb)"] += 1 if kb else 0

print(f"писем партии: {len(ряд)}")
for к, n in свод.most_common():
    print(f"  {n:>5}  {к}")
if длины:
    длины.sort()
    print(f"\nдлина этой единственной строки: медиана {длины[len(длины)//2]} "
          f"знаков, максимум {длины[-1]}")
for к, (cid, т) in пример.items():
    print(f"  пример ({к}) #{cid}: {т}")
