# -*- coding: utf-8 -*-
"""Сколько писем партии стоит в очереди и все ли тексты собраны верно."""
import re, sys
from collections import Counter
sys.path.insert(0, r"C:\sender")
from sender.store import Store                                 # noqa: E402

# ТЕМ ТЕПЕРЬ ШЕСТЬ. После раскладки по вариантам счётчик по одной теме
# видел шестую часть партии и показывал 491 письмо вместо 2560.
sys.path.insert(0, r"C:\sender\server\ops")
import varianty_pisma as V                                      # noqa: E402
store = Store(r"C:\sender\sender.db")
счёт = Counter()
битые = []
with store._lock:
    for р in store._conn.execute(
            "SELECT id, status, body, email FROM confirm_reviews "
            " WHERE subject IN (%s)" % ",".join("?" * len(V.ТЕМЫ)),
            tuple(V.ТЕМЫ)):
        счёт[str(р["status"])] += 1
        т = str(р["body"] or "")
        if "ИМЯ_ОТПРАВИТЕЛЯ" not in т:
            битые.append((р["id"], р["email"], "нет метки имени"))
        elif "{" in т or "}" in т:
            битые.append((р["id"], р["email"], "осталась фигурная скобка"))
        elif "удаление эгилопса и овсюга" not in т:
            # Опознаём ДЕЙСТВУЮЩИЙ текст, а не прошлый: прежняя проверка
            # искала «выращивает зерновые культуры» - фразу письма с
            # подстановкой названия, которой в нынешнем тексте нет вовсе, и
            # честно ругалась на все 2897 карточек сразу.
            битые.append((р["id"], р["email"], "не текст партии"))
        elif "\u2014" in т:
            битые.append((р["id"], р["email"], "длинное тире"))
        elif re.search(r"«[^»]*«|»[^«]*»[^ ,.]", т):
            битые.append((р["id"], р["email"], "двойные кавычки"))
        elif '"' in т:
            битые.append((р["id"], р["email"], "прямые кавычки"))
for i, п, ч in битые[:25]:
    print("   %-8s %-32s %s" % (i, str(п)[:32], ч))
print("")
print("=" * 70)
print("=== ОЧЕРЕДЬ ПАРТИИ ===")
for к, в in счёт.most_common():
    print("   %-20s %6d" % (к, в))
print("всего: %d; с замечаниями в тексте: %d" % (sum(счёт.values()), len(битые)))
