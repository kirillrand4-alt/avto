# -*- coding: utf-8 -*-
"""Только чтение: сверка метрики «непустых блоков» с соседней сессией.

Их метрика — все непустые ключи. Моя — только поля-факты. Считаю обе на
одних данных и на сегодняшней партии, чтобы понять, сдвинута ли шкала."""
import io
import json
import os
import sqlite3
from collections import Counter

СУТЬ = {"продукция", "упаковка_фасовка", "сырьё", "мощности", "контроль_качества",
        "экспорт", "оборудование_линии", "клиенты", "год_основания",
        "география_поставок", "масштаб", "расширение", "газы", "энергохозяйство",
        "новости"}


def непусто(v):
    return v not in (None, "", [], {}, "нет")


def медиана(a):
    a = sorted(a)
    return a[len(a) // 2] if a else 0


def дец(a):
    a = sorted(a)
    return (a[len(a) // 10], a[-max(1, len(a) // 10)]) if a else (0, 0)


e = sqlite3.connect("file:C:/sender/enrich.db?mode=ro", uri=True)
e.row_factory = sqlite3.Row
карт = {}
ключей_в_карточке = Counter()
for р in e.execute("SELECT inn, facts_json FROM site_facts"):
    try:
        f = json.loads(р["facts_json"] or "{}")
    except Exception:
        continue
    все = sum(1 for v in f.values() if непусто(v))
    факты = sum(1 for k, v in f.items() if k in СУТЬ and непусто(v))
    карт[str(р["inn"])] = (все, факты, len(f))
    ключей_в_карточке[len(f)] += 1

print("=== ПРОВЕРКА ИХ ЦИФР ПО ВСЕЙ БАЗЕ site_facts ===")
print("  карточек: %d" % len(карт))
пуст = sum(1 for v in карт.values() if v[0] == 0)
print("  полностью пустых (0 непустых блоков): %d (%.1f%%)"
      % (пуст, 100.0 * пуст / len(карт)))
все_сп = [v[0] for v in карт.values()]
факт_сп = [v[1] for v in карт.values()]
print("  ИХ метрика (все непустые ключи): медиана %d, 10-90%% %d-%d, максимум %d"
      % (медиана(все_сп), дец(все_сп)[0], дец(все_сп)[1], max(все_сп)))
print("  МОЯ метрика (только поля-факты) : медиана %d, 10-90%% %d-%d, максимум %d"
      % (медиана(факт_сп), дец(факт_сп)[0], дец(факт_сп)[1], max(факт_сп)))
print("  размер схемы (ключей в карточке):",
      dict(ключей_в_карточке.most_common(6)))

# сегодняшняя партия из журнала
ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
сегодня = []
if os.path.exists(ЖУРНАЛ):
    for s in io.open(ЖУРНАЛ, encoding="utf-8"):
        try:
            z = json.loads(s)
        except Exception:
            continue
        if (str(z.get("день")) == "2026-08-31" and z.get("ок")
                and str(z.get("направление")) == "meyer"):
            сегодня.append(str(z.get("inn")))
сег = [карт[i] for i in set(сегодня) if i in карт]
print("\n=== СЕГОДНЯШНЯЯ ПАРТИЯ (годные meyer, %d ИНН, нашлось карточек %d) ==="
      % (len(set(сегодня)), len(сег)))
if сег:
    a = [v[0] for v in сег]
    f = [v[1] for v in сег]
    print("  ИХ метрика: медиана %d, 10-90%% %d-%d, минимум %d, пустых %d"
          % (медиана(a), дец(a)[0], дец(a)[1], min(a), sum(1 for x in a if x == 0)))
    print("  МОЯ метрика (факты): медиана %d, 10-90%% %d-%d, минимум %d"
          % (медиана(f), дец(f)[0], дец(f)[1], min(f)))

print("\n=== СКОЛЬКО СЛУЖЕБНЫХ В «БЛОКАХ» ===")
разн = [v[0] - v[1] for v in карт.values()]
print("  все_непустые минус факты: медиана %d, среднее %.1f"
      % (медиана(разн), sum(разн) / max(1, len(разн))))

print("\n=== ИТОГ: чему их порог равен в фактах ===")
print("  %-18s %10s %14s" % ("их порог", "карточек", "медиана фактов"))
for п in (1, 3, 5, 7, 10):
    гр = [v[1] for v in карт.values() if v[0] >= п]
    print("  %-18s %10d %14d" % ("все блоки >= %d" % п, len(гр), медиана(гр)))
