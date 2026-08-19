# -*- coding: utf-8 -*-
"""Снять мейеровские письма, которым инженерная линза трижды сказала «не наш».

Перезапись 19.08: шесть писем не вышли с трёх попыток. У трёх причина одна
и та же и не про текст - линза читает сайт и говорит, что компания не
производство: консультации, продажа швейного оборудования, торговля
металлопрокатом со склада. Старое письмо про пищевую сортировку при этом
лежит в очереди и уйдёт, если оператор его подтвердит.

Снимаем ТОЛЬКО тех, у кого причина - профиль компании. Текстовые огрехи
(дубль слова, не названо предприятие) не трогаем: там письмо рабочее.

Без аргумента - сухой прогон.
"""
import io
import json
import os
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

Ж = r"C:\sender\_ops\peregeneraciya-meyer.jsonl"
СВОЙ = r"C:\sender\_ops\snyatye-ne-nashi-meyer.jsonl"
КАТИТЬ = "--катить" in sys.argv
ПРИЗНАК = "инженерная линза"

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

последние, успех = {}, set()
for s in io.open(Ж, encoding="utf-8", errors="replace"):
    try:
        z = json.loads(s)
    except Exception:                                            # noqa: BLE001
        continue
    i = int(z["id"])
    if z.get("ок"):
        успех.add(i)
    последние[i] = z

к_снятию = []
for i, z in последние.items():
    if i in успех:
        continue
    row = store.confirm_get(i) or {}
    if row.get("status") != "pending":
        continue
    ф = " | ".join(str(x) for x in (z.get("fails") or []))
    if ПРИЗНАК not in ф:
        continue
    к_снятию.append((i, row.get("company_name") or z.get("фирма"), ф[:200]))

print(f"к снятию (не наш адресат по линзе): {len(к_снятию)}")
for i, имя, ф in к_снятию:
    print(f"  #{i}  {str(имя)[:40]:<42} {ф[:90]}")
if not к_снятию or not КАТИТЬ:
    print("\nсухой прогон: ничего не тронуто. Катить — аргумент --катить"
          if к_снятию else "снимать нечего")
    raise SystemExit(0)

снято = 0
for i, имя, ф in к_снятию:
    try:
        ок = store.confirm_decide(
            i, status="skipped",
            reason=f"не наш адресат: {ф[:200]}",
            decided_by="инженерная линза, три попытки перезаписи 19.08")
        if ок is False:
            карточка = store.confirm_get(i) or {}
            mid = карточка.get("message_id")
            if mid:
                store.mark_skipped(int(mid), "не наш адресат (линза)")
        снято += 1
        with io.open(СВОЙ, "a", encoding="utf-8") as f:
            f.write(json.dumps({"id": i, "фирма": имя, "почему": ф},
                               ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
    except Exception as ex:                                      # noqa: BLE001
        print(f"  #{i}: {type(ex).__name__} {str(ex)[:100]}")
print(f"\nснято: {снято}")
