# -*- coding: utf-8 -*-
r"""Шапка CSV догруза и одна строка — чем на самом деле названы колонки."""
import io
import json

with io.open(r'C:\sender\_tmp\partiya-935-dogruz.csv', encoding='utf-8-sig') as f:
    первые = [next(f, '').rstrip('\n') for _ in range(3)]
print(json.dumps({'строки': [s[:300] for s in первые]}, ensure_ascii=False, indent=1))
