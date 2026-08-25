# -*- coding: utf-8 -*-
"""ПРЕДПОЛЁТ перед добором контактов из кэша.

1) горячая копия базы через VACUUM INTO;
2) проверка НА САМОЙ КОПИИ (integrity_check + счётчики против оригинала);
3) формат телефонов в базе (чтобы писать в том же виде);
4) свежий пересчёт списка целей.
В боевую базу НИЧЕГО не пишет: VACUUM INTO только читает источник.
"""
import json
import os
import sqlite3
import time

BD = r'C:\sender\enrich.db'
RO = 'file:C:/sender/enrich.db?mode=ro'
KESH = r'C:\seostat\drop\pagecache'
KOPIYA = r'C:\sender\_tmp\enrich-pered-kesh-doborom-%s.db' % time.strftime('%Y%m%d-%H%M')

print('размер enrich.db: %.2f ГБ' % (os.path.getsize(BD) / 2 ** 30))
for suf in ('-wal', '-shm'):
    p = BD + suf
    if os.path.exists(p):
        print('  %s: %.1f МБ' % (suf, os.path.getsize(p) / 2 ** 20))

# --- 1. горячая копия ---
t0 = time.time()
c = sqlite3.connect(RO, uri=True, timeout=60)
c.execute('PRAGMA busy_timeout=60000')
c.execute("VACUUM INTO ?", (KOPIYA,))
c.close()
print('КОПИЯ: %s (%.2f ГБ) за %.0f сек' % (KOPIYA, os.path.getsize(KOPIYA) / 2 ** 30,
                                           time.time() - t0))

# --- 2. проверка на копии ---
k = sqlite3.connect('file:%s?mode=ro' % KOPIYA.replace('\\', '/'), uri=True, timeout=60)
print('integrity_check:', k.execute('PRAGMA integrity_check').fetchone()[0])
o = sqlite3.connect(RO, uri=True, timeout=60)
sverka = {}
for t in ('companies', 'emails', 'phone_contacts', 'people', 'site_facts', 'stage_log',
          'email_sources'):
    a = o.execute('select count(*) from "%s"' % t).fetchone()[0]
    b = k.execute('select count(*) from "%s"' % t).fetchone()[0]
    sverka[t] = {'оригинал': a, 'копия': b, 'сходится': a == b}
print('СВЕРКА:', json.dumps(sverka, ensure_ascii=False))
print('копия читается выборкой:', k.execute(
    "select count(*) from emails where coalesce(source,'')<>''").fetchone()[0])

# --- 3. формат телефонов ---
print('форматы phone в базе:', json.dumps(
    [list(r) for r in o.execute(
        'select phone, count(*) n from phone_contacts group by phone order by n desc limit 5')],
    ensure_ascii=False))
print('примеры phone:', json.dumps(
    [r[0] for r in o.execute('select distinct phone from phone_contacts limit 12')],
    ensure_ascii=False))
print('источники в phone_contacts:', json.dumps(
    [list(r) for r in o.execute(
        'select coalesce(source,\'\'), count(*) n from phone_contacts group by 1 '
        'order by n desc limit 8')], ensure_ascii=False)[:700])
print('источники в emails:', json.dumps(
    [list(r) for r in o.execute(
        "select coalesce(source,''), count(*) n from emails group by 1 order by n desc limit 8")],
    ensure_ascii=False)[:700])

# --- 4. свежий список целей ---
s_email = {str(r[0]) for r in o.execute('select distinct inn from emails')}
s_phone = {str(r[0]) for r in o.execute('select distinct inn from phone_contacts')}
komp = {str(r[0]) for r in o.execute('select inn from companies')}
o.close()
k.close()
kesh = [n.split('.')[0] for n in os.listdir(KESH) if n.endswith('.json.gz')]
celi = sorted(i for i in kesh if i not in s_email and i not in s_phone and i in komp)
print('ЦЕЛИ СЕЙЧАС: %d (в замере было 1265)' % len(celi))
staryj = json.load(open(r'C:\sender\_tmp\dyra3.json', encoding='utf-8'))['celi']
print('  из старого списка осталось без контактов: %d из %d'
      % (len(set(celi) & set(staryj)), len(staryj)))

with open(r'C:\sender\_tmp\kesh-dobor-predpolyot.json', 'w', encoding='utf-8') as f:
    json.dump({'kopiya': KOPIYA, 'sverka': sverka, 'celi': celi,
               'kogda': time.strftime('%Y-%m-%dT%H:%M:%S')}, f, ensure_ascii=False)
    f.flush()
    os.fsync(f.fileno())
print('ИТОГ: предполёт записан, копия готова')
