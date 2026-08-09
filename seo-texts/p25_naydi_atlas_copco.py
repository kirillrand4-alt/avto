# -*- coding: utf-8 -*-
"""Найти базу по Atlas Copco и посмотреть, что в ней. Владелец сказал: где-то лежит, влейте.

На дропе виден `atlas_copco.db-shm` — это спутник ОТКРЫТОЙ sqlite-базы, значит сама база
где-то рядом и её кто-то держал открытой. Ищу по дискам сервера, печатаю схему и объёмы.

Только чтение.
"""
import json
import os
import sqlite3

KORNI = [r'C:\sender', r'C:\seostat', r'C:\ClaudeProjects']
naydeno = []
for koren in KORNI:
    if not os.path.isdir(koren):
        continue
    for dp, dn, fn in os.walk(koren):
        dn[:] = [d for d in dn if d not in ('.git', 'node_modules', '__pycache__')]
        for f in fn:
            fl = f.lower()
            if 'atlas' in fl or 'copco' in fl:
                p = os.path.join(dp, f)
                try:
                    naydeno.append((p, os.path.getsize(p)))
                except Exception:  # noqa: BLE001
                    pass

print('=== ФАЙЛЫ С ИМЕНЕМ ATLAS/COPCO')
for p, n in sorted(naydeno, key=lambda x: -x[1])[:30]:
    print('  %10d  %s' % (n, p))
if not naydeno:
    print('  не найдено')

print('\n=== ЧТО ВНУТРИ БАЗ')
for p, n in naydeno:
    if not p.lower().endswith('.db') or n < 1000:
        continue
    try:
        cx = sqlite3.connect('file:%s?mode=ro' % p.replace('\\', '/'), uri=True)
        tabl = [r[0] for r in cx.execute(
            "select name from sqlite_master where type='table'")]
        print('\n  --- %s (%d байт)' % (p, n))
        for t in tabl:
            try:
                k = cx.execute('select count(*) from "%s"' % t).fetchone()[0]
                kol = [r[1] for r in cx.execute('pragma table_info("%s")' % t)]
                print('      %-26s %7d  %s' % (t, k, kol[:14]))
                if k:
                    r = cx.execute('select * from "%s" limit 2' % t).fetchall()
                    for row in r:
                        print('         %s' % json.dumps(
                            {kk: (str(vv)[:80] if vv is not None else '')
                             for kk, vv in zip(kol, row)}, ensure_ascii=False)[:400])
            except Exception as e:  # noqa: BLE001
                print('      %-26s ошибка %s' % (t, str(e)[:60]))
        cx.close()
    except Exception as e:  # noqa: BLE001
        print('  %s: не открылась — %s' % (p, str(e)[:80]))

print('\nИТОГ ' + json.dumps({'файлов': len(naydeno)}, ensure_ascii=False))
