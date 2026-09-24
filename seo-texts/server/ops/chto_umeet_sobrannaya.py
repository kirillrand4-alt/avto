# -*- coding: utf-8 -*-
"""Что умеет собранный SPA на сервере: ищем строки экранов в бандле."""
import io
import os

БАНДЛ = r"C:\sender\sender\web\dist\assets\index-C1NCQk_j.js"
if not os.path.exists(БАНДЛ):
    п = r"C:\sender\sender\web\dist\assets"
    кандидаты = [os.path.join(п, x) for x in os.listdir(п) if x.endswith(".js")]
    БАНДЛ = кандидаты[0] if кандидаты else ""
print("бандл: %s (%d байт)" % (БАНДЛ, os.path.getsize(БАНДЛ) if БАНДЛ else 0))

т = io.open(БАНДЛ, encoding="utf-8", errors="replace").read()
МАРКЕРЫ = [
    "Переписка со всей компанией",
    "Переписка",
    "lead-dialog",
    "/dialog",
    "ответ клиента",
    "Потребность",
    "Логи событий",
    "Что случилось",
    "показать целиком",
    "письмо не доставлено",
    "отказ почтовика",
    "не интересно",
]
print("")
print("--- какие строки есть в собранной панели ---")
for м in МАРКЕРЫ:
    print("   %-34s %s" % (м, "ЕСТЬ" if м in т else "НЕТ"))

# как режется текст лида в ленте
import re
print("")
print("--- обрезки в бандле (slice по числу) ---")
for м in sorted(set(re.findall(r"\.slice\(0,\s*(\d+)\)", т)), key=lambda x: int(x))[:14]:
    print("   slice(0, %s)" % м)
print("")
print("=" * 74)
print("=== ЧТО УМЕЕТ СОБРАННАЯ ПАНЕЛЬ ===")
