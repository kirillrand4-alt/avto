# -*- coding: utf-8 -*-
r"""Что за время лежит в addr_probe.ts — момент пробы или момент загрузки?"""
import json, re
t = open(r'C:\sender\sender\addr_probe.py', encoding='utf-8', errors='replace').read()
i = t.find('def _save')
d = {'_save': t[i:i+1500] if i > 0 else 'нет'}
p = open(r'C:\sender\sender\probe_sync.py', encoding='utf-8', errors='replace').read()
j = p.find('def забрать')
d['забрать'] = p[j:j+1800] if j > 0 else 'нет'
print(json.dumps(d, ensure_ascii=False, indent=1)[:3600])
