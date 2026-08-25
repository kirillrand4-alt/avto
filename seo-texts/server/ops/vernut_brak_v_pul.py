# -*- coding: utf-8 -*-
"""Вернуть в пул генерации фирмы, чьи письма сняли ПО КАЧЕСТВУ ТЕКСТА.

Владелец 25.08: «включая скипы — где причина не то что мы уже писали, а то
что письмо тогда не нравилось». В живом partiya_gen возвращались только
«не наш / вне профиля / не покупатель / механическая сборка» — то есть
брак линзы и правил стиля оставался лежать, и мой замер обещал больше, чем
дал бы прогон.

ЧТО ДОБАВЛЯЕМ. Линзу (кроме её же направленческих вердиктов), человечность,
рекламные обороты, старьё до 10.08 и административные снятия под партию.

ЧЕГО НЕ ДОБАВЛЯЕМ. Всё, где сказано про НАПРАВЛЕНИЕ: «линза: направление:
фотосепаратор виноградному соку» — это про компанию, а не про текст, и
другим письмом не лечится. Поэтому у линзы стоит явный вычет.

    pl_run.py vernut_brak_v_pul.py            # вхолостую
    pl_run.py vernut_brak_v_pul.py primenit   # применить
"""
import io
import py_compile
import shutil
import sqlite3
import sys
import time

ПУТЬ = r"C:\sender\_ops\partiya_gen.py"
ПРИМЕНИТЬ = "primenit" in sys.argv[1:]

ЯКОРЬ = ('                "  OR c.reason LIKE \'%механическая сборка%\')").fetchall():')
ЗАМЕНА = (
    '                "  OR c.reason LIKE \'%механическая сборка%\' "\n'
    '                # ПИСЬМО БЫЛО ПЛОХИМ — фирма возвращается, текст будет\n'
    '                # другим (владелец 25.08). Направленческие вердикты той\n'
    '                # же линзы вычитаем: «фотосепаратор виноградному соку» —\n'
    '                # это про компанию, другим письмом не лечится.\n'
    '                "  OR (c.reason LIKE \'%линза%\' '
    'AND c.reason NOT LIKE \'%направлени%\') "\n'
    '                "  OR c.reason LIKE \'%человечност%\' "\n'
    '                "  OR c.reason LIKE \'%реклама%\' "\n'
    '                "  OR c.reason LIKE \'%написанное до 2026-08-10%\' "\n'
    '                "  OR c.reason LIKE \'%чужая кампания%\')").fetchall():')

т = io.open(ПУТЬ, encoding="utf-8").read()
if "ПИСЬМО БЫЛО ПЛОХИМ" in т:
    print("правка уже стоит")
    raise SystemExit(0)
н = т.count(ЯКОРЬ)
print("якорь найден %d раз" % н)
if н != 1:
    raise SystemExit("ОТМЕНА: якорь должен встречаться ровно один раз")

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
было = c.execute(
    "SELECT COUNT(DISTINCT r.inn) FROM confirm_reviews c2 "
    "  LEFT JOIN recipients r ON r.id=c2.recipient_id "
    " WHERE c2.status='skipped' AND (c2.reason LIKE '%не наш%' "
    "   OR c2.reason LIKE '%вне профиля%' OR c2.reason LIKE '%не покупатель%' "
    "   OR c2.reason LIKE '%механическая сборка%')").fetchone()[0]
станет = c.execute(
    "SELECT COUNT(DISTINCT r.inn) FROM confirm_reviews c2 "
    "  LEFT JOIN recipients r ON r.id=c2.recipient_id "
    " WHERE c2.status='skipped' AND (c2.reason LIKE '%не наш%' "
    "   OR c2.reason LIKE '%вне профиля%' OR c2.reason LIKE '%не покупатель%' "
    "   OR c2.reason LIKE '%механическая сборка%' "
    "   OR (c2.reason LIKE '%линза%' AND c2.reason NOT LIKE '%направлени%') "
    "   OR c2.reason LIKE '%человечност%' OR c2.reason LIKE '%реклама%' "
    "   OR c2.reason LIKE '%написанное до 2026-08-10%' "
    "   OR c2.reason LIKE '%чужая кампания%')").fetchone()[0]
print("фирм возвращается сейчас: %d, станет: %d (прибавка %d)"
      % (было, станет, станет - было))

if not ПРИМЕНИТЬ:
    print("\nвхолостую. Применить — primenit")
    raise SystemExit(0)
метка = time.strftime("%Y%m%d-%H%M%S")
shutil.copy2(ПУТЬ, ПУТЬ + ".bak-" + метка)
try:
    io.open(ПУТЬ, "w", encoding="utf-8", newline="").write(т.replace(ЯКОРЬ, ЗАМЕНА))
    py_compile.compile(ПУТЬ, doraise=True)
except Exception as e:  # noqa: BLE001
    print("СБОЙ: %s — откатываю" % e)
    shutil.copy2(ПУТЬ + ".bak-" + метка, ПУТЬ)
    raise
print("правлен partiya_gen.py (копия .bak-%s)" % метка)
