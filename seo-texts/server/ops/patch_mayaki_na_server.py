# -*- coding: utf-8 -*-
"""Выкатить маяки на боевой sender/.

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
ПОСЫЛКА = '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'
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

есть_модуль = os.path.exists(os.path.join(КОРЕНЬ, "mayaki.py"))
print(f"\nmayaki.py на сервере: {'есть' if есть_модуль else 'нет'}; "
      f"наш {len(ДАННЫЕ['модуль'])} знаков")

if not КАТИТЬ:
    print("\nсухой прогон, ничего не записано. Катить - --katit")
    raise SystemExit(0)

if беда:
    print("\nСТОП: часть якорей не сошлась, выкатываем ВСЁ или НИЧЕГО.")
    raise SystemExit(1)

_записать("mayaki.py", ДАННЫЕ["модуль"])
for имя, текст in готово.items():
    _записать(имя, текст)

sys.path.insert(0, r"C:\sender")
for м in list(sys.modules):
    if м.startswith("sender."):
        sys.modules.pop(м, None)
from sender.mayaki import nastroyki, spisok                        # noqa: E402
from sender.config import Config as _Cfg                           # noqa: E402
_c = _Cfg.load(r"C:\\sender\\sender.yaml")
print(f"\nпроба: настройки {nastroyki(_c)}, маяков в конфиге {len(spisok(_c))}")
print("ПАНЕЛЬ НАДО ПЕРЕЗАПУСТИТЬ: Restart-Service SenderPanel -Force")
