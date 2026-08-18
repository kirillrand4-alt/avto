# -*- coding: utf-8 -*-
"""Как письмо, собранное из карточки, противоречит сайту — по трём колонкам.

Вопрос владельца: «мы же собрали его из карточки с сайта». Значит надо
положить рядом три вещи и посмотреть глазами:
  1) что говорит КАРТОЧКА (activity + откуда взято, подтверждён ли источник);
  2) что утверждает ПИСЬМО (первые фразы про производство);
  3) в чём претензия РЕЦЕНЗЕНТА (что он увидел на сайте).

Заодно считаем, у скольких «противоречий» карточка сама помечена как
непроверенная — тогда это не выдумка генератора, а чужие факты в карточке.

    python zapusk_svoego_skripta.py ops/otkuda_protivorechie.py [сколько]
"""
import io
import json
import re
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

СКОЛЬКО = int(next((a for a in sys.argv[1:] if a.isdigit()), "8"))
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

последний = {}
for s in io.open(r"C:\sender\_ops\rezenzii-pisem.jsonl", encoding="utf-8",
                 errors="replace"):
    try:
        z = json.loads(s)
        последний[int(z["id"])] = z
    except Exception:                                            # noqa: BLE001
        continue
плохие = {i: z for i, z in последний.items()
          if str(z.get("verdict") or "") == "не годно"}

ключи = ",".join("?" * len(плохие))
with store._lock:
    ряд = store._conn.execute(
        f"SELECT id, body, panel_json FROM confirm_reviews WHERE id IN ({ключи})",
        list(плохие)).fetchall()

свод = Counter()
показать = []
for cid, тело, pj in ряд:
    try:
        p = json.loads(pj or "{}")
    except Exception:                                            # noqa: BLE001
        p = {}
    c = p.get("company") if isinstance(p.get("company"), dict) else {}
    активность = (c.get("activity") or "").strip()
    подтв = bool(c.get("activity_verified"))
    ист = (c.get("activity_source") or "").strip()
    если = ("карточка подтверждена сайтом" if подтв and ист
            else ("источник назван, не подтверждён" if ист
                  else ("описания нет" if not активность
                        else "ИСТОЧНИК ПОТЕРЯН")))
    свод[если] += 1
    if len(показать) < СКОЛЬКО and подтв and ист:
        показать.append((cid, активность, ист, тело, плохие[cid]))

print(f"«не годно» с разбором карточки: {sum(свод.values())}")
for к, n in свод.most_common():
    print(f"  {n:>4}  {к}")

print("\n=== случаи, где карточка ПОДТВЕРЖДЕНА сайтом, а письмо всё равно"
      " разошлось с ним")
for cid, активность, ист, тело, рец in показать:
    фразы = [x.strip() for x in re.split(r"(?<=[.!?])\s+",
                                         re.sub(r"<[^>]+>", " ", тело or ""))
             if x.strip()]
    начало = " ".join(фразы[1:4])[:300]
    print(f"\n#{cid} {str(рец.get('фирма'))[:44]}   сайт: {рец.get('url')}")
    print(f"  КАРТОЧКА: «{активность[:150]}»")
    print(f"            источник: {ист}")
    print(f"  ПИСЬМО:   {начало}")
    print(f"  РЕЦЕНЗЕНТ: {str((рец.get('pretenzii') or [''])[0])[:260]}")
