# -*- coding: utf-8 -*-
"""Заменить длинное тире на дефис в карточках вебинара 28.08.

Правило репозитория: длинных тире в письмах нет. Тексты вебинара писал
владелец, и в них тире осталось - меняем в теме и теле, у карточек в
статусе pending (решённые не трогаем: их текст уже ушёл или отвергнут).

Ловим ВСЕ длинные варианты, а не только U+2014: в текстах, прошедших
через редакторы, попадаются ещё среднее тире и минус.
Без аргумента - сухой прогон.
"""
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                              # noqa: E402
from sender.store import Store                                # noqa: E402

ТИРЕ = {"\u2014": "-", "\u2013": "-", "\u2012": "-", "\u2212": "-",
        "\u2015": "-"}
писать = len(sys.argv) > 1 and sys.argv[1] == "primenit"
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))


def чинить(т):
    for плохое, хорошее in ТИРЕ.items():
        т = т.replace(плохое, хорошее)
    # «слово - слово» с неразрывным пробелом до дефиса выглядит как ошибка
    return т.replace("\u00a0-", " -")


with store._lock:
    строки = store._conn.execute(
        "SELECT id, subject, body, status FROM confirm_reviews "
        " WHERE dedup_key LIKE 'vebinar28:%' ORDER BY id").fetchall()

надо, всего_тире = [], 0
for кид, тема, тело, статус in строки:
    т2, б2 = чинить(тема or ""), чинить(тело or "")
    if (т2, б2) == (тема, тело):
        continue
    сколько = sum((тема or "").count(з) + (тело or "").count(з) for з in ТИРЕ)
    всего_тире += сколько
    if статус != "pending":
        print(f"  №{кид}: {сколько} тире, но статус {статус} — не трогаю")
        continue
    надо.append((кид, т2, б2, сколько))

print(f"карточек: {len(строки)}, с длинным тире: "
      f"{len(надо)} (всего вхождений {всего_тире})")
if not писать:
    if надо:
        кид, т2, б2, _ = надо[0]
        print(f"\nпример №{кид} после правки:\n{б2[:400]}")
    print("\nсухой прогон: ничего не менял (primenit — записать)")
    raise SystemExit(0)

сделано = 0
with store._lock:
    for кид, т2, б2, _ in надо:
        store._conn.execute(
            "UPDATE confirm_reviews SET subject=?, body=?, "
            "updated_at=datetime('now') WHERE id=? AND status='pending'",
            (т2, б2, кид))
        сделано += 1
    store._conn.commit()
print(f"поправлено карточек: {сделано}")
