# -*- coding: utf-8 -*-
"""Точечная правка боевого api/app.py: «Потребность» лида — текстом.

Почему точечно, а не выкаткой файла целиком: серверная копия api/app.py
отличается от моей (2562 строки против 2575) — каталог делят несколько
сессий, и залить свой файл поверх значит увезти в бой чужие непроверенные
строки или, наоборот, стереть их. Правка одна, место одно, поэтому меняем
на месте, с бэкапом и проверкой единственности.

Что меняем: карточка лида отдаёт leads.need как есть, а это тело ответа
клиента, приходящее HTML-ом. В панели поле печатается как обычный текст,
и оператор видит «<div style="background-color:rgb( 255 , 255 , 255 )">»
вместо письма.

    python zapusk_svoego_skripta.py ops/pravka_lead_json_v_paneli.py
    python zapusk_svoego_skripta.py ops/pravka_lead_json_v_paneli.py --править
"""
import io
import shutil
import sys
import time

ПУТЬ = r"C:\sender\sender\api\app.py"
ПРАВИТЬ = "--править" in sys.argv

СТАРОЕ = '''            "phone": l.phone, "need": l.need, "assigned_to": l.assigned_to,'''
НОВОЕ = '''            "phone": l.phone, "need": _v_tekst(l.need),
            "assigned_to": l.assigned_to,'''
ЯКОРЬ = "def _lead_json(l):"
ВСТАВКА = '''def _v_tekst(текст):
    """Тело письма — в читаемый текст. Разбор один на панель."""
    try:
        from sender.pismo_v_tekst import v_tekst
        return v_tekst(текст)
    except Exception:                                           # noqa: BLE001
        return текст


'''

т = io.open(ПУТЬ, encoding="utf-8").read()
print(f"файл: {len(т)} знаков")
print(f"строк 'need': {т.count(СТАРОЕ)}")
print(f"правка уже стоит: {'_v_tekst(l.need)' in т}")
if "_v_tekst(l.need)" in т:
    print("нечего делать")
    raise SystemExit(0)
if т.count(СТАРОЕ) != 1 or т.count(ЯКОРЬ) != 1:
    print("ОТКАЗ: место правки не единственное — руками")
    raise SystemExit(2)

новый = т.replace(СТАРОЕ, НОВОЕ).replace(ЯКОРЬ, ВСТАВКА + ЯКОРЬ)
print(f"станет: {len(новый)} знаков (+{len(новый) - len(т)})")
if not ПРАВИТЬ:
    print("\nсухой прогон: файл не тронут. Править — аргумент --править")
    raise SystemExit(0)

бэкап = ПУТЬ + f".bak-{int(time.time())}"
shutil.copy2(ПУТЬ, бэкап)
io.open(ПУТЬ, "w", encoding="utf-8", newline="").write(новый)
print(f"записано, бэкап: {бэкап}")

import py_compile                                                # noqa: E402
try:
    py_compile.compile(ПУТЬ, doraise=True)
    print("синтаксис ок")
except Exception as ex:                                          # noqa: BLE001
    shutil.copy2(бэкап, ПУТЬ)
    print(f"СИНТАКСИС СЛОМАН, откатил из бэкапа: {str(ex)[:200]}")
    raise SystemExit(3)
