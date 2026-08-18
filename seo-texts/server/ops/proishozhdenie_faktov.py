# -*- coding: utf-8 -*-
"""Откуда в карточке взялось описание деятельности — и знаем ли мы источник.

Карточка несёт три поля происхождения, и они честнее, чем кажется:
  activity          — чем компания занимается (на этом строится письмо);
  activity_source   — откуда описание взято («разбор сайта такого-то»);
  activity_verified — подтверждён ли источник.
У части компаний источник потерян, и карточка прямо предупреждает: описание
получено разбором сайта, но подтверждённого сайта в карточке нет, оно может
относиться к другой организации.

Отдельно считаем кириллические домены: рецензент их не снял, и это похоже
не на «сайта нет», а на то, что до него не дотянулись.

    python zapusk_svoego_skripta.py ops/proishozhdenie_faktov.py
"""
import io
import json
import re
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
КИРИЛЛИЦА = re.compile(r"[а-яА-ЯёЁ]")

нечем = {}
for s in io.open(r"C:\sender\_ops\rezenzii-pisem.jsonl", encoding="utf-8",
                 errors="replace"):
    try:
        z = json.loads(s)
    except Exception:                                            # noqa: BLE001
        continue
    if str(z.get("verdict") or "") == "нечем проверить":
        нечем[int(z["id"])] = z

урлы = [str(z.get("url") or "").strip() for z in нечем.values()]
кир = [u for u in урлы if u and КИРИЛЛИЦА.search(u)]
лат = [u for u in урлы if u and not КИРИЛЛИЦА.search(u)]
print(f"«нечем проверить»: {len(нечем)}")
print(f"  домен кириллицей (.рф и т.п.): {len(кир)}  напр. {кир[:6]}")
print(f"  домен латиницей, текст не снят: {len(лат)}  напр. {лат[:6]}")
print(f"  URL нет вовсе:                 {len(урлы) - len(кир) - len(лат)}")


def _разбор(строки, заголовок):
    свод = Counter()
    примеры = {}
    for cid, pj in строки:
        try:
            p = json.loads(pj or "{}")
        except Exception:                                        # noqa: BLE001
            continue
        c = p.get("company") if isinstance(p.get("company"), dict) else {}
        есть = bool((c.get("activity") or "").strip())
        подтв = bool(c.get("activity_verified"))
        ист = (c.get("activity_source") or "").strip()
        if not есть:
            ключ = "описания деятельности нет вовсе"
        elif подтв and ист:
            ключ = f"подтверждено, источник назван"
        elif ист:
            ключ = "источник назван, но не подтверждён"
        else:
            ключ = "ИСТОЧНИК ПОТЕРЯН (карточка сама предупреждает)"
        свод[ключ] += 1
        примеры.setdefault(ключ, (cid, (c.get("activity") or "")[:70], ист))
    print(f"\n{заголовок} (всего {sum(свод.values())}):")
    for к, n in свод.most_common():
        cid, akt, ист = примеры[к]
        print(f"  {n:>5}  {к}")
        print(f"         напр. #{cid}: «{akt}» источник: {ист or '—'}")


ключи = ",".join("?" * len(нечем))
with store._lock:
    строки = store._conn.execute(
        f"SELECT id, panel_json FROM confirm_reviews WHERE id IN ({ключи})",
        list(нечем)).fetchall()
_разбор(строки, "происхождение фактов у «нечем проверить»")

with store._lock:
    все = store._conn.execute(
        "SELECT id, panel_json FROM confirm_reviews "
        "WHERE campaign_id=10 AND status IN ('pending','approved','sent')"
    ).fetchall()
_разбор(все, "то же по всей партии 935")
