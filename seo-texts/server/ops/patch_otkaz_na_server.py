# -*- coding: utf-8 -*-
"""Выкатить учёт отказов почтовика и автостоп на боевой sender/.

ЧТО ВЕЗЁМ: новый модуль otkaz_spam.py плюс правки шести файлов — событие
reject_spam, немедленная пауза ящика и направления, метрики в аналитике,
гейт reject_rate в «Сработавшие гейты», mailbox_id при неудачной отправке.

ХИРУРГИЯ, А НЕ ПЕРЕЗАПИСЬ. Каталог C:\\sender\\sender делят несколько
сессий: сегодняшний серверный фронт собран из исходников, которых нет в
гите, и целиковая заливка снесла бы чужую работу. Поэтому каждый кусок
меняется по ЯКОРЮ и только если якорь найден РОВНО ОДИН раз; иначе файл не
трогаем вовсе и говорим об этом. Перед записью .bak, после записи —
компиляция.

Фронт этим опом НЕ трогается: бандл собран не из наших исходников.

Сухой прогон по умолчанию. Катить: --katit
"""
import base64
import io
import json
import os
import py_compile
import sys
import time
import zlib

КОРЕНЬ = r"C:\sender\sender"
КАТИТЬ = "--katit" in sys.argv
ПОСЫЛКА = "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"
ДАННЫЕ = json.loads(zlib.decompress(base64.b64decode(ПОСЫЛКА)).decode())


def _записать(имя, текст):
    путь = os.path.join(КОРЕНЬ, имя.replace("sender/", "").replace("/", os.sep))
    if os.path.exists(путь):
        копия = f"{путь}.bak-{int(time.time())}"
        io.open(копия, "w", encoding="utf-8", newline="").write(
            io.open(путь, encoding="utf-8").read())
    with io.open(путь, "w", encoding="utf-8", newline="") as f:
        f.write(текст)
        f.flush()
        os.fsync(f.fileno())
    py_compile.compile(путь, doraise=True)
    print(f"  записан: {имя} ({len(текст)} знаков)")


готово, беда = {}, []
for имя, куски in ДАННЫЕ["пары"].items():
    путь = os.path.join(КОРЕНЬ, имя.replace("sender/", ""))
    try:
        т = io.open(путь, encoding="utf-8").read()
    except Exception as ex:                                        # noqa: BLE001
        беда.append(f"{имя}: не прочитан ({str(ex)[:60]})")
        continue
    новый, применено, пропущено = т, 0, 0
    for было, стало in куски:
        if стало in новый and было not in новый:
            пропущено += 1            # уже стоит
            continue
        n = новый.count(было)
        if n != 1:
            беда.append(f"{имя}: якорь встречается {n} раз — "
                        f"{было.splitlines()[0][:50]!r}")
            новый = None
            break
        новый = новый.replace(было, стало, 1)
        применено += 1
    if новый is None:
        continue
    готово[имя] = новый
    print(f"{имя}: кусков {len(куски)}, применено {применено}, "
          f"уже стояло {пропущено}, было {len(т)} знаков, станет {len(новый)}")

if беда:
    print("\nНЕ ТРОГАЕМ (якорь не сошёлся):")
    for б in беда:
        print("  " + б)

есть_модуль = os.path.exists(os.path.join(КОРЕНЬ, "otkaz_spam.py"))
print(f"\notkaz_spam.py на сервере: {'есть' if есть_модуль else 'нет'}; "
      f"наш {len(ДАННЫЕ['модуль'])} знаков")

if not КАТИТЬ:
    print("\nсухой прогон, ничего не записано. Катить - --katit")
    raise SystemExit(0)

if беда:
    print("\nСТОП: часть якорей не сошлась, выкатываем ВСЁ или НИЧЕГО.")
    raise SystemExit(1)

_записать("otkaz_spam.py", ДАННЫЕ["модуль"])
for имя, текст in готово.items():
    _записать(имя, текст)

sys.path.insert(0, r"C:\sender")
for м in list(sys.modules):
    if м.startswith("sender."):
        sys.modules.pop(м, None)
from sender.otkaz_spam import eto_otkaz_spam                       # noqa: E402
проба = ("(554, b'5.7.1 Message rejected under suspicion of SPAM; "
         "https://ya.cc/1IrBc')")
мимо = "(550, b'invalid mailbox.  Local mailbox x@mail.ru is unavailable')"
print(f"\nпроба разбора: отказ={eto_otkaz_spam(проба)} (ждём True), "
      f"мёртвый ящик={eto_otkaz_spam(мимо)} (ждём False)")
print("ПАНЕЛЬ НАДО ПЕРЕЗАПУСТИТЬ: Restart-Service SenderPanel -Force")
