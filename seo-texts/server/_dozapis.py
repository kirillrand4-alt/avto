# -*- coding: utf-8 -*-
"""Перенести накопленное в базу (перекачка уже сделана, тексты в jsonl)."""
import importlib.util, json, os, sys
sys.path.insert(0, r'C:\sender\server'); os.chdir(r'C:\sender\server')
spec = importlib.util.spec_from_file_location('ds', r'C:\sender\server\dobor_slabyh.py')
ds = importlib.util.module_from_spec(spec); spec.loader.exec_module(ds)
print('===ИТОГ===')
print(json.dumps(ds.обновить(), ensure_ascii=False, indent=1))
