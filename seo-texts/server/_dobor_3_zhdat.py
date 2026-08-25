# -*- coding: utf-8 -*-
"""Ждать окончания добора (в итоговом файле появляется ключ 'секунд')."""
import json
import os
import time

ZH = r'C:\sender\_tmp\kesh-dobor.jsonl'
IT = r'C:\sender\_tmp\kesh-dobor-itog.json'
SROK = 500

t0 = time.time()
gotovo = False
while time.time() - t0 < SROK:
    try:
        d = json.load(open(IT, encoding='utf-8'))
        if 'секунд' in d:
            gotovo = True
            break
    except Exception:  # noqa: BLE001
        pass
    time.sleep(15)
n = 0
if os.path.exists(ZH):
    with open(ZH, encoding='utf-8') as f:
        n = sum(1 for _ in f)
print('строк журнала:', n, '| закончено:', gotovo, '| ждал', round(time.time() - t0), 'сек')
try:
    print(json.dumps(json.load(open(IT, encoding='utf-8')), ensure_ascii=False)[:700])
except Exception as e:  # noqa: BLE001
    print('итог:', str(e)[:80])
