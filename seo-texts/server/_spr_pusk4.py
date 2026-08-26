# -*- coding: utf-8 -*-
"""Пуск съёма promrnd.ru отвязанным процессом + текущий прогресс."""
import io
import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')
ФЛАГИ = 0x00000008 | 0x00000200
лог = r'C:\sender\_tmp\spr_promrnd.log'
ф = open(лог, 'a', encoding='utf-8')
p = subprocess.Popen([sys.executable, r'C:\sender\_tmp\_spr_promrnd2.py', 'sbor'],
                     stdout=ф, stderr=subprocess.STDOUT, cwd=r'C:\sender\_tmp',
                     creationflags=ФЛАГИ)
O = {'pid': p.pid}
for f, k in (('spr_dokaz.jsonl', 'доказ'), ('ozav_cards.jsonl', 'ozav'),
             ('agro_cards.jsonl', 'agro'), ('promrnd_cards.jsonl', 'promrnd')):
    pp = r'C:\sender\_tmp\%s' % f
    O[k] = sum(1 for _ in io.open(pp, encoding='utf-8', errors='replace')) \
        if os.path.exists(pp) else 0
print(json.dumps(O, ensure_ascii=False))
