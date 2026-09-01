# -*- coding: utf-8 -*-
"""97 писем, снятых за «нет представления первой строкой»: что с ними.

Правило (ai_letter.py:3725) для Meyer в режиме GENERIC простое: в теле
должно встречаться «меня зовут», и имя обязано быть меткой ИМЯ_ОТПРАВИТЕЛЯ.
Тела писем лежат в журнале — значит починка возможна без новой генерации.
"""
import io
import json
from collections import Counter

ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
свои = []
with io.open(ЖУРНАЛ, encoding="utf-8") as f:
    for с in f.readlines()[-9000:]:
        try:
            z = json.loads(с)
        except Exception:                                     # noqa: BLE001
            continue
        if z.get("этап") != "итог" or z.get("ок"):
            continue
        if "нет представления первой строкой" not in str(z.get("брак") or ""):
            continue
        свои.append(z)
print("писем с этой причиной: %d" % len(свои))
с_телом = [z for z in свои if z.get("тело")]
print("из них с сохранённым телом: %d" % len(с_телом))
print("дни: %s" % dict(Counter(z.get("день") for z in свои)))
print("направления: %s" % dict(Counter(z.get("направление") for z in свои)))

прочие = Counter()
for z in свои:
    try:
        сп = json.loads(str(z.get("брак") or "[]").replace("'", '"'))
    except Exception:                                         # noqa: BLE001
        сп = [str(z.get("брак"))]
    for п in сп:
        if "нет представления" not in str(п):
            прочие[str(п)[:70]] += 1
print("\nчто ЕЩЁ им вменили (кроме представления):")
for п, n in прочие.most_common(8):
    print("   %3d  %s" % (n, п))
только_это = sum(1 for z in свои
                 if str(z.get("брак") or "").count("'") <= 2)
print("   писем, где это ЕДИНСТВЕННАЯ причина: %d" % только_это)

print("\n=== ТРИ ПРИМЕРА ===")
for z in с_телом[:3]:
    print("\n-- %s (ИНН %s)" % (z.get("имя"), z.get("inn")))
    print("   тема: %s" % z.get("тема"))
    for стр in str(z.get("тело") or "").splitlines()[:8]:
        print("   | %s" % стр[:120])
