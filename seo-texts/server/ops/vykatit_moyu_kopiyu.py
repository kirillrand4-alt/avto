# -*- coding: utf-8 -*-
"""Выкатить MOYO-<имя> из _ops поверх боевого файла пакета sender.

Порядок обязателен и он же защита: сначала ops/sverit_s_moim.py показывает
diff (каталог общий с соседней сессией), и только если различия — ровно
мои, запускается это. Здесь ещё раз: копия .bak с отметкой, запись,
сверка sha256 после записи.

Запуск: python vykatit_moyu_kopiyu.py <имя файла в пакете sender>
"""
import hashlib
import io
import os
import shutil
import sys
import time

имя = sys.argv[1]
боевой = os.path.join(r"C:\sender\sender", имя.replace("/", os.sep))
моё = os.path.join(r"C:\sender\_ops", "MOYO-" + os.path.basename(имя))


def sha(путь):
    return hashlib.sha256(io.open(путь, "rb").read()).hexdigest()[:16]


было, стало = sha(боевой), sha(моё)
print(f"боевой {было} | моё {стало}")
if было == стало:
    print("уже одинаковые — выкатывать нечего")
    raise SystemExit(0)
рез = боевой + ".bak-" + time.strftime("%m%d-%H%M")
shutil.copy2(боевой, рез)
print("бэкап:", рез)
shutil.copy2(моё, боевой)
после = sha(боевой)
print(f"после записи: {после} — {'СОШЛОСЬ' if после == стало else 'РАЗОШЛОСЬ'}")
# Синтаксис боевого файла — до того, как его подхватит служба.
import py_compile                                              # noqa: E402
py_compile.compile(боевой, doraise=True)
print("компилируется")
