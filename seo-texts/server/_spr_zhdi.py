# -*- coding: utf-8 -*-
"""Подождать и доложить прогресс (сон на сервере, чтобы не жечь вызовы)."""
import io
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
time.sleep(float(sys.argv[1]) if len(sys.argv) > 1 else 480)
O = {}
for f in ('ozav_cards.jsonl', 'agro_cards.jsonl', 'spr_dokaz.jsonl'):
    p = r'C:\sender\_tmp\%s' % f
    O[f] = sum(1 for _ in io.open(p, encoding='utf-8', errors='replace')) \
        if os.path.exists(p) else 0
for f in ('spr_ozav.log', 'spr_agro.log', 'spr_dokaz.log'):
    try:
        O.setdefault('логи', {})[f] = open(r'C:\sender\_tmp\%s' % f,
                                           encoding='utf-8', errors='replace').read()[-70:]
    except Exception as e:
        O.setdefault('логи', {})[f] = str(e)[:40]
print(json.dumps(O, ensure_ascii=False))
