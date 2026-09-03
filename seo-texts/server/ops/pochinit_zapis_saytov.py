# -*- coding: utf-8 -*-
"""Сделать запись найденного сайта устойчивой к занятой базе.

sayty_dlya_celey.py падает на первой же компании с «database is locked»:
за пишущий замок enrich.db сейчас дерутся ходилка, доливка и сверка. Сам
поиск при этом отработал и результат лёг в журнал — теряется только запись
в базу, а с ней и весь прогон.

Оборачиваем upsert_company в повторы и делаем его необязательным: журнал
sayty_dlya_celey.jsonl пишется в любом случае, и по нему всё доливается.

Файл общий: якорь, бэкап, проверка компиляции, откат при неудаче.
Запуск: python pochinit_zapis_saytov.py [--primenit]
"""
import io
import os
import py_compile
import shutil
import sys
import time

П = r"C:\sender\server\ops\sayty_dlya_celey.py"
ПРИМЕНИТЬ = "--primenit" in sys.argv or "--apply" in sys.argv

ЯКОРЬ = """        if not СУХОЙ:
            if совпал:
                db.upsert_company(c['inn'], site=сайт)
            else:
                db.upsert_company(c['inn'], cand_site=сайт)"""
ЗАМЕНА = """        if not СУХОЙ:
            # БАЗА ЗАНЯТА — НЕ ПОВОД ВАЛИТЬ ПРОГОН (03.09). Здесь прогон
            # падал на первой же компании с «database is locked»: за
            # пишущий замок enrich.db дерутся ходилка, доливка и сверка.
            # Поиск при этом уже оплачен и его результат лежит в журнале,
            # так что терять весь прогон из-за записи нельзя. Повторяем, а
            # не вышло — идём дальше: журнал долить можно всегда, деньги за
            # повторный запрос вернуть нельзя.
            for _поп in range(6):
                try:
                    if совпал:
                        db.upsert_company(c['inn'], site=сайт)
                    else:
                        db.upsert_company(c['inn'], cand_site=сайт)
                    break
                except Exception as _ex:  # noqa: BLE001
                    if 'locked' not in str(_ex) and 'busy' not in str(_ex):
                        raise
                    time.sleep(3.0)
            else:
                print('  запись в базу не легла (занята), сайт в журнале')"""

т = io.open(П, encoding="utf-8", errors="replace").read()
шаги = []
if "БАЗА ЗАНЯТА — НЕ ПОВОД ВАЛИТЬ ПРОГОН" in т:
    шаги.append("файл уже правлен")
elif ЯКОРЬ not in т:
    шаги.append("ЯКОРЬ НЕ НАЙДЕН — не трогаю")
    for i, с in enumerate(т.splitlines(), 1):
        if "upsert_company" in с:
            шаги.append("   строка %d: %s" % (i, с[:120]))
elif ПРИМЕНИТЬ:
    бэкап = П + ".bak-%d" % int(time.time())
    shutil.copy2(П, бэкап)
    io.open(П, "w", encoding="utf-8").write(т.replace(ЯКОРЬ, ЗАМЕНА, 1))
    try:
        py_compile.compile(П, doraise=True)
        шаги.append("правка применена, компилируется; бэкап %s"
                    % os.path.basename(бэкап))
    except Exception as ex:                                    # noqa: BLE001
        shutil.copy2(бэкап, П)
        шаги.append("НЕ КОМПИЛИРУЕТСЯ (%s) — откатил" % str(ex)[:70])
else:
    шаги.append("якорь найден, готов править (сухой прогон)")

# есть ли import time
есть_time = "\nimport time" in т or "\nimport time\n" in т
print("=" * 76)
print("=== СВОДКА: ПОЧИНКА ЗАПИСИ САЙТОВ ===")
print("режим: %s" % ("ПРИМЕНЕНО" if ПРИМЕНИТЬ else "СУХОЙ ПРОГОН"))
print("import time в файле: %s" % ("есть" if есть_time else "НЕТ — добавить"))
for с in шаги:
    print("   " + с)
