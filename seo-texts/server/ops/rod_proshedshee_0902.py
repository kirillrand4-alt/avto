# -*- coding: utf-8 -*-
"""Только чтение: где в партии 13 прошедшее время первого лица."""
import re
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
import sender.gender_agree as GA  # noqa: E402

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row

print("=== ГДЕ ВСТРЕЧАЕТСЯ «был» ===")
for р in c.execute("SELECT email, body FROM confirm_reviews WHERE campaign_id=13"
                   " AND LOWER(body) LIKE '%был%'"):
    for стр in str(р["body"]).splitlines():
        if "был" in стр.lower():
            print("  %-30s %s" % (р["email"][:30], стр.strip()[:96]))

print("\n=== ГЛАГОЛЫ ПРОШЕДШЕГО ВРЕМЕНИ ОТ ПЕРВОГО ЛИЦА ===")
# ищем «я ...л» и «...л вам/вас» — то, что движок не согласует
шаблон = re.compile(r"(?<![а-яё])(я\s+[а-яё]+л|[а-яё]+л\s+(?:вам|вас|вашей|вашему))",
                    re.I)
найдено = {}
for р in c.execute("SELECT email, body FROM confirm_reviews WHERE campaign_id=13"):
    for м in шаблон.finditer(str(р["body"])):
        ф = м.group(0).lower()
        найдено.setdefault(ф, []).append(р["email"])
if not найдено:
    print("  не нашлось ни одного")
for ф, сп in sorted(найдено.items(), key=lambda x: -len(x[1]))[:14]:
    print("  «%-24s» в %3d письмах | движок в женском: «%s»"
          % (ф, len(сп), GA.agree(ф, "f")))

print("\n=== ЕЩЁ РАЗ ПРО ВСЕ КРАТКИЕ ФОРМЫ ===")
for сл in ("благодарен", "признателен", "готов", "рад", "уверен", "должен",
           "намерен", "обязан", "способен", "заинтересован"):
    k = c.execute("SELECT COUNT(*) FROM confirm_reviews WHERE campaign_id=13"
                  " AND LOWER(body) LIKE ?", ("%" + сл + "%",)).fetchone()[0]
    if k:
        рез = GA.agree("Буду " + сл + " за ответ.", "f")
        ок = сл not in рез.lower()
        print("  %-14s %3d писем | %s | %s"
              % (сл, k, рез.strip()[:34], "переводится" if ок else "НЕ ПЕРЕВОДИТСЯ"))
