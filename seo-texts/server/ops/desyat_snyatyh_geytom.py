# -*- coding: utf-8 -*-
"""Десять компаний, снятых гейтом адресата — глазами.

Владелец спросил, можно ли вердикт гейта «не покупатель» записывать в
вечный реестр. Вердикт выносит модель, и только в последнем прогоне так
снято 100 компаний. Прежде чем вычёркивать навсегда, надо посмотреть, на
чём он основан: что гейт написал в chem/pochemu и что говорит паспорт
сайта той же компании.
"""
import json
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.ai_quota import build_ai_quota                       # noqa: E402
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

СКОЛЬКО = int(next((a for a in sys.argv[1:] if a.isdigit()), "10"))
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
print("вердикты гейта в базе:")
for r in c.execute("SELECT verdict, COUNT(*) n FROM target_verdicts "
                   "GROUP BY verdict ORDER BY n DESC"):
    print(f"  {r['n']:>6}  {r['verdict']}")

ряды = c.execute(
    "SELECT tv.inn, tv.verdict, COALESCE(tv.chem,'') chem, "
    "       COALESCE(tv.pochemu,'') pochemu, COALESCE(tv.source,'') src, "
    "       (SELECT company_name FROM recipients WHERE inn=tv.inn LIMIT 1) имя, "
    "       (SELECT okved FROM recipients WHERE inn=tv.inn LIMIT 1) оквэд "
    "FROM target_verdicts tv WHERE tv.verdict NOT IN ('покупатель','buyer') "
    "ORDER BY tv.ts DESC LIMIT ?", (СКОЛЬКО,)).fetchall()

for r in ряды:
    print("=" * 76)
    print(f"ИНН {r['inn']} · {str(r['имя'] or '')[:44]}")
    print(f"  ОКВЭД: {str(r['оквэд'] or '')[:70]}")
    print(f"  вердикт гейта: {r['verdict']} (источник {r['src']})")
    if r["chem"]:
        print(f"  чем занимается: {r['chem'][:220]}")
    if r["pochemu"]:
        print(f"  почему не покупатель: {r['pochemu'][:260]}")
    try:
        д = q._site_facts(str(r["inn"])) or {}
    except Exception:                                            # noqa: BLE001
        д = {}
    прод = д.get("продукция") or []
    цит = str(д.get("цитата") or "")
    if прод or цит:
        print(f"  ПАСПОРТ продукция: {json.dumps(прод, ensure_ascii=False)[:200]}")
        print(f"  ПАСПОРТ цитата: {цит[:180]}")
    else:
        print("  ПАСПОРТ: пусто")
