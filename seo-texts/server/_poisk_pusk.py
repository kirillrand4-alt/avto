# -*- coding: utf-8 -*-
r"""Снять холд поиска сайтов и поднять прогон (провайдер остаётся под холдом)."""
import json
import os
import sys
import time

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
os.chdir(DIR)

итог = {}
флаг = os.path.join(DIR, 'HOLD-POISK.flag')
if os.path.exists(флаг):
    os.replace(флаг, флаг + '.snyat-' + time.strftime('%Y%m%d-%H%M%S'))
    итог['холд_поиска'] = 'снят'
else:
    итог['холд_поиска'] = 'его и не было'
итог['холд_провайдера'] = ('на месте' if os.path.exists(
    os.path.join(DIR, 'HOLD-FAKTY.flag')) else 'ОТСУТСТВУЕТ — проверить!')

import storozh as S  # noqa: E402
итог['сторож'] = S.обход()
time.sleep(20)
итог['крутится_поиск'] = bool(S._крутится(S._живые(), 'poisk_saytov.py'))
лог = r'C:\sender\poisk_saytov.out'
if os.path.exists(лог):
    with open(лог, encoding='utf-8', errors='replace') as f:
        итог['хвост_лога'] = f.read()[-700:]
print(json.dumps(итог, ensure_ascii=False, indent=1))
