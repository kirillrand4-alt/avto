# -*- coding: utf-8 -*-
"""Переписать пищевые письма, где назван только один станок Meyer.

Правило поправлено (для пищевого профиля два станка - норма), но письма в
очереди написаны по старому: замер 19.08 показал 38 писем с одним рентгеном
против восьми с обоими. Берём только pending.
"""
import re
import sys
import time
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.ai_quota import build_ai_quota                       # noqa: E402
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

РЕНТГЕН = re.compile(r'(?i)рентген|инспекци\w*\s+упаков|металлодетект')
ФОТО = re.compile(r'(?i)фотосепарат|оптическ\w*\s+сортиров|'
                  r'сортировк\w*\s+(сырь|зерн|орех|крупы)')
ПИЩЕВОЙ = re.compile(
    r'(?i)кондитер|готов\w*\s+(еда|блюд|кулинар)|полуфабрикат|выпечк|'
    r'снек|орех|сухофрукт|мюсли|батончик|шоколад|печень|пряник|конфет|'
    r'десерт|мороженое|хлебобулочн')

КАТИТЬ = "--катить" in sys.argv
ПОТОЛОК = int(next((a for a in sys.argv[1:] if a.isdigit()), "20"))
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)

with store._lock:
    ряды = store._conn.execute(
        "SELECT id, COALESCE(edited_body, body, '') FROM confirm_reviews "
        "WHERE status='pending' AND campaign_id IN (7,8,9,11)").fetchall()
работа = []
for rid, тело in ряды:
    т = str(тело or "")
    if not ПИЩЕВОЙ.search(т):
        continue
    if bool(РЕНТГЕН.search(т)) != bool(ФОТО.search(т)):   # ровно один станок
        работа.append(int(rid))
работа = работа[:ПОТОЛОК]
print(f"к переписыванию: {len(работа)} — {работа}")
if not работа or not КАТИТЬ:
    print("сухой прогон. Катить — аргумент --катить" if работа
          else "переписывать нечего")
    raise SystemExit(0)

итоги = Counter()
t0 = time.time()
for rid in работа:
    try:
        res = q.regenerate_review(int(rid))
    except Exception as ex:                                      # noqa: BLE001
        итоги[f"сбой: {type(ex).__name__}"] += 1
        continue
    ок = bool(res.get("ok"))
    итоги["переписано" if ок else f"отказ: {str(res.get('reason'))[:40]}"] += 1
    if ок:
        строка = store.confirm_get(int(rid)) or {}
        т = строка.get("body") or ""
        оба = bool(РЕНТГЕН.search(т)) and bool(ФОТО.search(т))
        итоги["  и назвал оба станка" if оба
              else "  но станок опять один"] += 1
    print(f"  #{rid}: {'ОК' if ок else res.get('reason')}")
print(f"\nготово за {time.time() - t0:.0f}с")
for k, n in итоги.most_common():
    print(f"  {n:>3}  {k}")
