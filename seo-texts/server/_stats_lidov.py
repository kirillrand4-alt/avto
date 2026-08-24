# -*- coding: utf-8 -*-
r"""Откуда берётся stats.by_status в ручке /leads — считает ли он ВСЕ статусы."""
import json
import re

d = {}
п = r'C:\sender\sender\api\app.py'
строки = open(п, encoding='utf-8', errors='replace').read().splitlines()
нач = next((i for i, s in enumerate(строки) if re.search(r'def leads\(|"/leads"', s)), 0)
d['ручка'] = ['%d: %s' % (i + 1, строки[i].strip()[:130])
              for i in range(нач, min(len(строки), нач + 40))]
т = open(r'C:\sender\sender\store.py', encoding='utf-8', errors='replace').read()
м = re.search(r'def lead_stats.{0,1500}?(?=\n    def )', т, re.S)
d['lead_stats'] = [s.strip()[:130] for s in (м.group(0) if м else '').splitlines()][:20]
print(json.dumps(d, ensure_ascii=False, indent=1)[:3000])
