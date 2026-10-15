# -*- coding: utf-8 -*-
r"""fixL (15.10): только чтение. Архив кода панели на дроп (fixL-kod.zip), схема базы продаж, состояние тестовой
компании 7130001590, ID вариантов «Нет» у полей «Торгующая компания?» (crm.lead.fields – чтение справочника).
Ссылка вебхука не печатается."""
import io
import json
import os
import sqlite3
import time
import urllib.request
import zipfile

APP = r'C:\centro2\app'
D = r'C:\seostat\drop\drop-storage'
OUT = os.path.join(D, 'fixL-kod.zip')
n = 0
with zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED) as z:
    for d, dirs, fs in os.walk(APP):
        if 'dokaz' in d.split(os.sep) or '__pycache__' in d:
            continue
        for f in fs:
            if f.endswith(('.py', '.html', '.css', '.js')):
                p = os.path.join(d, f)
                if os.path.getsize(p) > 3_000_000:
                    continue
                z.write(p, os.path.relpath(p, APP))
                n += 1
    for f in ('zapusk.py',):
        p = os.path.join(r'C:\centro2', f)
        if os.path.exists(p):
            z.write(p, '_koren/' + f)
print('кода файлов: %d (%d байт)' % (n, os.path.getsize(OUT)))
B = r'C:\centro2\data\centro_sales_meyer1.db'
c = sqlite3.connect('file:%s?mode=ro' % B, uri=True)
for (nm, sq) in c.execute("select name, sql from sqlite_master where type in ('table','view') order by name"):
    print('TABLE', nm, ':', (sq or '').replace('\n', ' ')[:600])
INN = '7130001590'
for t in ('company_assignment', 'company_state', 'company_comment', 'zvonok_sobytie', 'activity_log'):
    try:
        kol = [x[1] for x in c.execute('pragma table_info(%s)' % t)]
        pole = 'inn' if 'inn' in kol else None
        if pole:
            rows = c.execute('select * from %s where inn=?' % t, (INN,)).fetchall()
        else:
            rows = []
        print('ROWS', t, kol, rows[:10])
    except Exception as e:  # noqa: BLE001
        print('ERR', t, e)
k = sqlite3.connect('file:%s?mode=ro' % r'C:\centro2\data\meyer_baza1.db', uri=True)
print('company cols:', [x[1] for x in k.execute('pragma table_info(company)')])
print('contact cols:', [x[1] for x in k.execute('pragma table_info(contact)')])
print('person cols:', [x[1] for x in k.execute('pragma table_info(person)')])
r = k.execute('select inn, predpriyatie, region, meyer_verdikt, meyer_verdikt_napravlenie, segment, otrasl from company where inn=?', (INN,)).fetchone()
print('company 7130001590:', r)
print('замок:', os.path.exists(r'C:\centro2\_zamok.txt'), time.strftime('%Y-%m-%d %H:%M:%S'))
if os.path.exists(r'C:\centro2\_zamok.txt'):
    print('   ', io.open(r'C:\centro2\_zamok.txt', encoding='utf-8').read())
try:
    W = io.open(r'C:\centro2\data\bitrix-webhook.secret', encoding='utf-8').read().strip()
    with urllib.request.urlopen(W + 'crm.lead.fields.json', timeout=30) as o:
        pole = json.loads(o.read().decode('utf-8'))['result']
    for kod in ('UF_CRM_61B6C14B0E2A1', 'UF_CRM_1639366376', 'UF_CRM_1711628077'):
        p = pole.get(kod) or {}
        print('POLE', kod, p.get('formLabel') or p.get('listLabel') or p.get('title'), p.get('type'), p.get('isMultiple'),
              [(x.get('ID'), x.get('VALUE')) for x in (p.get('items') or [])])
    for kod in ('SOURCE_ID', 'STATUS_ID', 'ASSIGNED_BY_ID', 'UF_CRM_68B688D287BE4'):
        p = pole.get(kod) or {}
        print('POLE', kod, p.get('type'), p.get('isMultiple'), p.get('title'))
except Exception as e:  # noqa: BLE001
    print('битрикс: ошибка чтения полей', type(e).__name__)
