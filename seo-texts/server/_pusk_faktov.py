# -*- coding: utf-8 -*-
r"""Снять холд провайдера и поднять цикл фактов на ночь.

Владелец 20.08: «восьмикратно не надо, давай как предложил сразу запускай на
всю ночь, но с проверкой ручной 3 раза каждые 5 минут».

Перед запуском проверяем то, из-за чего прошлые ночные прогоны шли вхолостую:
ключ провайдера должен быть виден процессу, который поднимает сторож от SYSTEM.
Если ключа нет — холд НЕ снимаем и ничего не поднимаем.
"""
import json
import os
import sys
import time

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
os.chdir(DIR)
import storozh as S  # noqa: E402

итог = {}
среда = S._sreda_faktov()
итог['настройки'] = {k: (v[:6] + '…' if k.endswith('KEY') and v else v)
                     for k, v in среда.items()}
есть_ключ = bool(среда.get('PROVIDER_API_KEY') or os.environ.get('PROVIDER_API_KEY'))
итог['ключ_провайдера_виден'] = есть_ключ
if not есть_ключ:
    итог['ИТОГ'] = 'ключа нет — холд не снимаю, цикл не поднимаю'
    print(json.dumps(итог, ensure_ascii=False, indent=1))
    raise SystemExit(1)

флаг = os.path.join(DIR, 'HOLD-FAKTY.flag')
if os.path.exists(флаг):
    os.replace(флаг, флаг + '.snyat-' + time.strftime('%Y%m%d-%H%M%S'))
    итог['холд'] = 'снят'
else:
    итог['холд'] = 'его и не было'

итог['сторож'] = S.обход()
time.sleep(20)
итог['крутится_цикл'] = bool(S._крутится(S._живые(), 'fakty_cikl.py'))
лог = r'C:\sender\server\fakty_cikl.log'
if os.path.exists(лог):
    with open(лог, encoding='utf-8', errors='replace') as f:
        итог['хвост_лога'] = f.read()[-500:]
print(json.dumps(итог, ensure_ascii=False, indent=1))
