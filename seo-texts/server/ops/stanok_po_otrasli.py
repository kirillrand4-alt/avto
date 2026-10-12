# -*- coding: utf-8 -*-
"""Проставить получателям партий главный станок Meyer по отрасли.

18 из 24 браков «переставить на КЦ» в запуске 12.10 — письма пластику,
металлургии, лесу, горнодобыче и вторсырью, написанные как РЕНТГЕНОВСКИЕ:
станок угадывается по ОКВЭД, а в карте градаций только пищевые коды, и всё
прочее по умолчанию уходит в рентген. Линза справедливо отвечает, что
пластику и щебню рентген не нужен. Генератор читает станок из
extra_json.meyer_gradaciya — ставим его по отрасли книги.

Запуск: stanok_po_otrasli.py [--primenit]
"""
import io
import json
import os
import sys
import time
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.store import Store  # noqa: E402

ПРИМЕНИТЬ = "--primenit" in sys.argv
ФОТО = {"Пластик и полимеры", "Стекло", "Горнодобыча, нерудные",
        "Вторсырьё и лом", "Лес и деревообработка", "Металлургия",
        "Химия, удобрения", "Зерно, мука, элеваторы, семена",
        "Овощи, фрукты, орехи, ягоды", "Масложир (МЭЗ)", "Кофе, чай, специи"}
РЕНТГЕН = {"Мясо, птица, молоко", "Хлеб, кондитерка, макароны",
           "Опт продуктами", "Прочая пищевка, корма, фасовка"}
ГРУППЫ = ("Россия 9000", "Белорусь 1000")
store = Store(r"C:\sender\sender.db")
свод = Counter()
правки = []
with store._lock:
    for р in store._conn.execute(
            "SELECT id, segment, extra_json FROM recipients "
            "WHERE extra_json LIKE '%gruppy%'"):
        try:
            д = json.loads(р["extra_json"] or "{}") or {}
        except Exception:  # noqa: BLE001
            continue
        if not any(г in (д.get("gruppy") or []) for г in ГРУППЫ):
            continue
        отр = р["segment"] or ""
        станок = "фото" if отр in ФОТО else "рентген" if отр in РЕНТГЕН else ""
        if not станок:
            свод["отрасль без правила"] += 1
            continue
        if д.get("meyer_gradaciya") == станок:
            свод["уже стоит"] += 1
            continue
        д["meyer_gradaciya"] = станок
        правки.append((json.dumps(д, ensure_ascii=False), р["id"]))
        свод[станок] += 1
    if ПРИМЕНИТЬ and правки:
        store._conn.executemany("UPDATE recipients SET extra_json=? WHERE id=?",
                                правки)
        store._conn.commit()
if ПРИМЕНИТЬ and правки:
    with io.open(r"C:\sender\_ops\stanok-po-otrasli.jsonl", "a",
                 encoding="utf-8") as ж:
        ж.write(json.dumps({"ts": int(time.time()), "правок": len(правки),
                            "свод": dict(свод)}, ensure_ascii=False) + "\n")
        ж.flush()
        os.fsync(ж.fileno())
for к, n in свод.most_common():
    print("   %-24s %5d" % (к, n))
print("=== СТАНОК ПО ОТРАСЛИ: %s, правок %d ==="
      % ("ПРИМЕНЕНО" if ПРИМЕНИТЬ else "сухой прогон", len(правки)))
