# -*- coding: utf-8 -*-
"""Только чтение: точный контекст «был» и финальная сверка партии 13."""
import re
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
import sender.gender_agree as GA  # noqa: E402

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
for р in c.execute("SELECT email, body FROM confirm_reviews WHERE campaign_id=13"
                   " AND LOWER(body) LIKE '%был%'"):
    for м in re.finditer(r"был", str(р["body"]), re.I):
        н, к = max(0, м.start() - 45), м.end() + 45
        print("  %-28s ...%s..." % (р["email"][:28],
                                    str(р["body"])[н:к].replace("\n", " ")))

print("\n=== ФИНАЛЬНАЯ СВЕРКА ПАРТИИ 13 ===")
всего = c.execute("SELECT COUNT(*) FROM confirm_reviews"
                  " WHERE campaign_id=13").fetchone()[0]
print("  писем: %d" % всего)
пров = {
    "метка ИМЯ_ОТПРАВИТЕЛЯ": "body LIKE '%ИМЯ_ОТПРАВИТЕЛЯ%'",
    "финал «С уважением,»": "body LIKE '%С уважением,%'",
    "есть вопрос": "body LIKE '%?%'",
    "длинное тире": "body LIKE '%—%'",
    "списки разметкой": "body LIKE '%<ul%' OR body LIKE '%<li%'",
    "слово вебинар": "body LIKE '%вебинар%'",
    "имя менеджера в теле": "body LIKE '%Меня зовут Артем%'"
                            " OR body LIKE '%Меня зовут Ирина%'"
                            " OR body LIKE '%Меня зовут Андрей%'",
}
for имя, усл in пров.items():
    k = c.execute("SELECT COUNT(*) FROM confirm_reviews WHERE campaign_id=13"
                  " AND (%s)" % усл).fetchone()[0]
    print("  %-24s %d" % (имя, k))

print("\n  слова, которые движок согласует по роду ящика:")
for сл in ("благодарен", "признателен", "готов", "рад", "уверен"):
    k = c.execute("SELECT COUNT(*) FROM confirm_reviews WHERE campaign_id=13"
                  " AND LOWER(body) LIKE ?", ("%" + сл + "%",)).fetchone()[0]
    if k:
        ж = GA.agree("Буду " + сл + ".", "f").strip()
        print("    %-14s %3d писем -> «%s»" % (сл, k, ж))
