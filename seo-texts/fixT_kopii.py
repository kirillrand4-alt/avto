# -*- coding: utf-8 -*-
r"""fixT (только чтение): md5 серверных копий скриптов, которые зовёт fixQ_zamena (3s_fixS_metki.py, 3s_fixS_ball.py),
наличие выгрузки Битрикса на дропе и состояние замка – сверить с репо перед заменой.

    python3 fixT_zapusk.py fixT_kopii.py
"""
import hashlib
import io
import os

OPS = r'C:\sender\_ops'
for f in ('3s_fixS_metki.py', '3s_fixS_ball.py', '3s_fixT_fixQ_zamena.py'):
    p = os.path.join(OPS, f)
    print(f, hashlib.md5(open(p, 'rb').read()).hexdigest() if os.path.exists(p) else 'НЕТ')
z = r'C:\seostat\drop\drop-storage\fixS-bitrix-0910.zip'
print('fixS-bitrix-0910.zip', os.path.getsize(z) if os.path.exists(z) else 'НЕТ')
Z = r'C:\centro2\_zamok.txt'
print('замок:', io.open(Z, encoding='utf-8').read() if os.path.exists(Z) else 'свободен')
