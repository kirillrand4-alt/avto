# -*- coding: utf-8 -*-
"""Есть ли у рассыльщика штатная команда загрузки получателей."""
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
итог = {}
p = r'C:\sender\sender\cli.py'
if os.path.exists(p):
    t = io.open(p, encoding='utf-8', errors='replace').read()
    итог['команды_cli'] = re.findall(r'add_parser\(\s*[\'"]([\w\-:]+)', t)[:40]
    итог['про_импорт'] = [l.strip()[:120] for l in t.splitlines()
                          if re.search(r'import|recipients|csv', l, re.I)][:25]
# функции store, которые пишут получателей
s = r'C:\sender\sender\store.py'
if os.path.exists(s):
    t = io.open(s, encoding='utf-8', errors='replace').read()
    итог['store_функции'] = [l.strip()[:110] for l in t.splitlines()
                             if re.match(r'\s*def ', l) and
                             re.search(r'recipient|import|upsert', l, re.I)][:20]
print(json.dumps(итог, ensure_ascii=False, indent=1)[:3000])
