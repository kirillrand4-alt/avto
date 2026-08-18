# -*- coding: utf-8 -*-
"""Откуда взялись факты в письмах, которые рецензенту нечем было проверить.

Вопрос владельца: «а откуда у нас по ним карточки фактов?». Вопрос по делу:
если сайта нет, то на чём построено утверждение письма о производстве.

Сначала разделяем два разных случая, которые в журнале выглядят одинаково:
  * URL у компании ПУСТОЙ — сайта мы не знаем вовсе;
  * URL есть, но текста не сняли (закрыт, редирект, таймаут, Cloudflare) —
    сайт существует, просто рецензент до него не дотянулся.
Это разные истории: во втором случае факты могли браться с сайта РАНЬШЕ,
при генерации, и проверить их можно, просто другим способом.

Потом смотрим, что вообще лежит в карточке письма (panel_json) — какие
источники дали генератору материал.

    python zapusk_svoego_skripta.py ops/otkuda_fakty_bez_sayta.py
"""
import io
import json
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

ж = r"C:\sender\_ops\rezenzii-pisem.jsonl"
нечем = {}
for s in io.open(ж, encoding="utf-8", errors="replace"):
    try:
        z = json.loads(s)
    except Exception:                                            # noqa: BLE001
        continue
    if str(z.get("verdict") or "") == "нечем проверить":
        нечем[int(z["id"])] = z

print(f"писем «нечем проверить»: {len(нечем)}")
с_урл = [z for z in нечем.values() if str(z.get("url") or "").strip()]
print(f"  URL известен, но текста не сняли: {len(с_урл)}")
print(f"  URL нет вовсе:                    {len(нечем) - len(с_урл)}")
print("  примеры с известным URL:",
      [str(z.get("url")) for z in с_урл[:8]])

if not нечем:
    raise SystemExit(0)

ключи = ",".join("?" * len(нечем))
with store._lock:
    ряд = store._conn.execute(
        f"SELECT id, inn, email, panel_json FROM confirm_reviews "
        f"WHERE id IN ({ключи})", list(нечем)).fetchall()

источники = Counter()
поля = Counter()
примеры = []
for cid, inn, email, pj in ряд:
    try:
        p = json.loads(pj or "{}")
    except Exception:                                            # noqa: BLE001
        p = {}
    for k in p:
        поля[k] += 1
    комп = p.get("company") if isinstance(p.get("company"), dict) else {}
    факты = p.get("site_facts") or p.get("сайт") or {}
    if факты:
        источники["факты с сайта (site_facts) в карточке ЕСТЬ"] += 1
    if (комп.get("activity") or "").strip():
        источники["описание деятельности из обогащения (activity)"] += 1
    if (комп.get("okved") or комп.get("okved_all") or "").strip():
        источники["ОКВЭД"] += 1
    об = p.get("obzvon") if isinstance(p.get("obzvon"), dict) else {}
    if об.get("equip_categories"):
        источники["категории оборудования из базы обзвона"] += 1
    if об.get("division"):
        источники["метка направления из базы обзвона"] += 1
    if p.get("news") or p.get("новость"):
        источники["новость"] += 1
    if len(примеры) < 4:
        примеры.append((cid, inn, комп, об, факты))

print("\nчто лежало в карточке (по всем 96):")
for и, n in источники.most_common():
    print(f"  {n:>4}  {и}")
print("\nполя карточки:", dict(поля.most_common(12)))

print("\n=== четыре карточки целиком (без текста письма)")
for cid, inn, комп, об, факты in примеры:
    print(f"\n--- письмо #{cid}, ИНН {inn}")
    print(f"  company: {json.dumps(комп, ensure_ascii=False)[:400]}")
    print(f"  obzvon:  {json.dumps(об, ensure_ascii=False)[:300]}")
    print(f"  site_facts: {json.dumps(факты, ensure_ascii=False)[:300]}")
