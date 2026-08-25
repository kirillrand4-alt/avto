# -*- coding: utf-8 -*-
"""Подождать, пока в журнале добора появится хотя бы N строк (или истечёт срок)."""
import json
import os
import time

ZH = r'C:\sender\_tmp\kesh-dobor.jsonl'
NADO = int(os.environ.get('DOBOR_NADO', '40'))
SROK = int(os.environ.get('DOBOR_SROK', '480'))

t0 = time.time()
n = 0
while time.time() - t0 < SROK:
    n = 0
    if os.path.exists(ZH):
        with open(ZH, encoding='utf-8') as f:
            n = sum(1 for _ in f)
    if n >= NADO:
        break
    time.sleep(15)
print('строк в журнале:', n, 'за', round(time.time() - t0), 'сек')
