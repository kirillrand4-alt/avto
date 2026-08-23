# -*- coding: utf-8 -*-
r"""Как идёт сбор: строки в файле и хвост лога."""
import json
import os
import time

d = {}
c = r'C:\sender\_ops\roli_sobrano.jsonl'
if os.path.exists(c):
    n = sum(1 for _ in open(c, encoding='utf-8', errors='replace'))
    d['собрано_компаний'] = n
    d['файл_обновлён_сек_назад'] = int(time.time() - os.path.getmtime(c))
л = r'C:\sender\server\roli_telefonov.log'
if os.path.exists(л):
    строки = [s.strip() for s in open(л, encoding='utf-8', errors='replace')
              if s.strip()]
    d['лог'] = [s[:170] for s in строки[-3:]]
print(json.dumps(d, ensure_ascii=False, indent=1))
