# -*- coding: utf-8 -*-
"""sha256 боевых файлов на сервере - чтобы не затирать чужую правку.

Каталог C:\\sender\\sender делят несколько сессий сразу. 17.08 выкатка
соседа легла поверх нашей за 21 секунду до старта прогона, и обе правки
поехали в работу вперемешку. С тех пор порядок такой: перед заливкой
сверяем sha256 серверного файла с тем, ОТ КОТОРОГО мы правили. Совпало -
заливаем; не совпало - сосед что-то изменил, и сначала разбираемся.

    python zapusk_svoego_skripta.py ops/sverit_sha_servera.py ai_letter.py ai_quota.py
"""
import hashlib
import io
import os
import sys

КОРЕНЬ = r"C:\sender\sender"
имена = sys.argv[1:] or ["ai_letter.py", "ai_quota.py", "sender.py"]

for имя in имена:
    путь = os.path.join(КОРЕНЬ, имя)
    try:
        b = io.open(путь, "rb").read()
    except Exception as ex:                                    # noqa: BLE001
        print(f"{имя}: НЕ ПРОЧИТАН ({str(ex)[:80]})")
        continue
    print(f"{имя}: sha256={hashlib.sha256(b).hexdigest()} байт={len(b)} "
          f"строк={b.count(b'chr')*0 + b.decode('utf-8', 'replace').count(chr(10))}")
