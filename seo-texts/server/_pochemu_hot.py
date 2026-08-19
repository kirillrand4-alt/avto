# -*- coding: utf-8 -*-
"""Тексты «горячих» лидов и порядок правил в классификаторе."""
import io
import json
import re
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
итог = {}
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
s.row_factory = sqlite3.Row
итог['горячие'] = [{'id': r['id'], 'компания': (r['company_name'] or '')[:26],
                    'текст': (r['need'] or '')[:150]}
                   for r in s.execute(
    "select id, company_name, need from leads where reply_kind='hot' "
    'order by id desc limit 8')]
s.close()
t = io.open(r'C:\sender\sender\reply_classify.py', encoding='utf-8',
            errors='replace').read()
# порядок проверок в главной функции
m = re.search(r'def classify.*?(?=\ndef |\Z)', t, re.S)
итог['classify'] = (m.group(0)[:2000] if m else '')
итог['есть_срез_цитаты'] = bool(re.search(r'цитат|quote|>\s|On .* wrote|'
                                          r'_обрезать|_bez_citaty|отрезать', t))
итог['куски_про_цитату'] = [l.strip()[:110] for l in t.splitlines()
                            if re.search(r'цитат|quote|wrote|^\s*>', l)][:8]
print(json.dumps(итог, ensure_ascii=False, indent=1)[:4200])
