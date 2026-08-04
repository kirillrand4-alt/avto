# -*- coding: utf-8 -*-
"""Где лежат уже выкачанные карточки площадки и сколько их. Считать, а не вспоминать.

Разбор текста карточек дал три закрытых предприятия на 314 карточках соседа. Но мой
собственный сбор (`tenderpro_harvest.py --kartochki`) шёл по ВСЕЙ площадке по словам
«компрессор», «воздуходувка» и прочим, и в его выгрузке порядка девяти тысяч карточек
с ПОЛНЫМ комментарием — обрезку я сняла 30.07. Если это так, приз лежит уже
скачанным, и просить догрузку не нужно вовсе.
"""
import csv
import glob
import json
import os
import sys

csv.field_size_limit(10 ** 8)
NASHLI = []
for shabl in (r'C:\sender\_ops\**\tp-kartochki*.csv', r'C:\sender\**\tp-kartochki*.csv',
              r'C:\seostat\**\tp-kartochki*.csv', r'C:\sender\_ops\**\tp-*.csv'):
    NASHLI += glob.glob(shabl, recursive=True)

for p in sorted(set(NASHLI)):
    try:
        with open(p, encoding='utf-8-sig', newline='') as f:
            r = csv.DictReader(f, delimiter=';')
            polya = r.fieldnames or []
            n = dlin = s_kom = 0
            for row in r:
                n += 1
                k = row.get('comment') or row.get('kommentariy') or ''
                if k:
                    s_kom += 1
                    dlin = max(dlin, len(k))
        print('%s\n    строк %d, с комментарием %d, самый длинный %d знаков'
              % (p, n, s_kom, dlin))
        print('    поля: %s' % ', '.join(polya))
    except Exception as e:  # noqa: BLE001
        print('%s -> не читается: %s' % (p, e))

print('ИТОГ ' + json.dumps({'найдено файлов': len(set(NASHLI))}, ensure_ascii=False))
