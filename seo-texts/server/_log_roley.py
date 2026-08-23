# -*- coding: utf-8 -*-
r"""Полный итог прогона подписей из лога."""
import json
import os

лог = r'C:\sender\server\roli_telefonov.log'
строки = [s.rstrip() for s in open(лог, encoding='utf-8', errors='replace')]
print('\n'.join(s[:160] for s in строки[-40:]))
ж = r'C:\sender\_ops\roli_telefonov.jsonl'
if os.path.exists(ж):
    хв = [s.strip() for s in open(ж, encoding='utf-8', errors='replace') if s.strip()]
    print('--- журнал, последние 3 ---')
    print('\n'.join(s[:200] for s in хв[-3:]))
