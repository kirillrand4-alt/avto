# -*- coding: utf-8 -*-
"""Что уже насчитано и лежит в C:\\sender\\_tmp."""
import json
import os
import time

for n in ('dyry-shema.json', 'dyra1.json', 'dyra1b.json', 'dyra2.json', 'dyra3.json',
          'diagnoz-dyry.json'):
    p = os.path.join(r'C:\sender\_tmp', n)
    if os.path.exists(p):
        print(n, os.path.getsize(p), 'байт,',
              time.strftime('%m-%d %H:%M', time.localtime(os.path.getmtime(p))))
        try:
            d = json.load(open(p, encoding='utf-8'))
            print('   ключи:', json.dumps(list(d)[:12], ensure_ascii=False))
        except Exception as e:  # noqa: BLE001
            print('   не читается:', str(e)[:80])
    else:
        print(n, '- НЕТ')
