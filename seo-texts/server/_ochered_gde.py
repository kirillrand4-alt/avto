# -*- coding: utf-8 -*-
r"""Состояние очереди зенки: сколько строк, сколько ИНН, сколько уже отработано."""
import json
import os

БАЗА = r'C:\sender\zenno'
итог = {'корень_есть': os.path.isdir(БАЗА)}
if итог['корень_есть']:
    итог['содержимое'] = sorted(os.listdir(БАЗА))[:60]
    for имя in ('ochered.txt', 'gotovo', 'razobrano', 'pagecache', 'komanda.txt',
                'dispetcher.json', 'zhurnal.txt'):
        p = os.path.join(БАЗА, имя)
        if os.path.isfile(p):
            строк, инн = 0, set()
            with open(p, encoding='utf-8', errors='replace') as f:
                for s in f:
                    строк += 1
                    ч = s.strip().split(';')
                    if ч and ч[0].strip().isdigit():
                        инн.add(ч[0].strip())
            итог[имя] = {'байт': os.path.getsize(p), 'строк': строк,
                         'уник_инн': len(инн), 'изменён': os.path.getmtime(p)}
        elif os.path.isdir(p):
            try:
                итог[имя + '/'] = len(os.listdir(p))
            except Exception as e:  # noqa: BLE001
                итог[имя + '/'] = str(e)[:80]
        else:
            итог[имя] = 'НЕТ'
print(json.dumps(итог, ensure_ascii=False, indent=1))
