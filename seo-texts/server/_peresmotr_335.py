# -*- coding: utf-8 -*-
"""Пересчитать годность у тех, кого подвёл coalesce: site='' при живом кандидате."""
import io
import json
import os
import sqlite3
import sys

sys.path.insert(0, r'C:\sender\server')
import godnost as G  # noqa: E402

c = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/enrich.db', uri=True)
пострадали = {str(r[0]) for r in c.execute(
    "select inn from companies where coalesce(site,'')='' and site is not null "
    "and coalesce(cand_site,'')<>''")}
c.close()

было = 0
строки = []
if os.path.exists(G.ВЕРДИКТЫ):
    for s in io.open(G.ВЕРДИКТЫ, encoding='utf-8'):
        try:
            d = json.loads(s)
        except Exception:
            continue
        было += 1
        if d['inn'] not in пострадали:
            строки.append(s.rstrip('\n'))
with io.open(G.ВЕРДИКТЫ, 'w', encoding='utf-8') as f:
    f.write('\n'.join(строки) + ('\n' if строки else ''))
    f.flush()
    os.fsync(f.fileno())
итог = {'пострадавших': len(пострадали), 'вердиктов_было': было,
        'вердиктов_осталось': len(строки)}
итог['пересчёт'] = G.прогон()
print(json.dumps(итог, ensure_ascii=False))
