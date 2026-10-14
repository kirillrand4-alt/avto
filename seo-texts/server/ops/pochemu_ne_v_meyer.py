# -*- coding: utf-8 -*-
"""Почему новые Meyer-компании (предкласс вне групп 14.10) не были в рассылке Meyer:
метка базы обзвона, реестр «не наш»/сделка, писали ли им (кампании), есть ли адрес."""
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
e = sqlite3.connect(r"C:\sender\enrich.db", timeout=30)
o = sqlite3.connect(r"C:\sender\obzvon-index.db", timeout=30)
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
инн = [str(r[0]) for r in e.execute("SELECT inn FROM companies WHERE verdikt_pochemu LIKE '%вне групп 14.10%' "
                                     "AND verdikt_napr IN ('мейер','оба')")]
try:
    from sender.ne_nash import build_ne_nash
    не_наш = set(build_ne_nash().набор(None) or [])
except Exception:  # noqa: BLE001
    не_наш = set()
метка, писали, адр = Counter(), Counter(), Counter()
for i in инн:
    р = o.execute("SELECT division FROM obzvon WHERE inn=?", (i,)).fetchone()
    метка["нет в базе обзвона" if р is None else (р[0] or "пусто")] += 1
    камп = [r[0] for r in c.execute("SELECT DISTINCT m.campaign_id FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                                    "WHERE r.inn=? AND m.status='sent'", (i,))]
    писали["никогда" if not камп else "писали: " + ",".join(map(str, sorted(камп)))] += 1
    в_rec = c.execute("SELECT count(*) FROM recipients WHERE inn=?", (i,)).fetchone()[0]
    адр["есть в получателях" if в_rec else "только в обогащении"] += 1
print("всего: %d; в реестре «не наш»/сделка: %d" % (len(инн), sum(1 for i in инн if i in не_наш)))
print("метка базы обзвона:", dict(метка.most_common()))
print("писали ли:", dict(писали.most_common(8)))
print("где адрес:", dict(адр))
print("кампании:", c.execute("SELECT id, name FROM campaigns").fetchall())
print("=== ПОЧЕМУ НЕ В MEYER ===")
