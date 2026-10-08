# -*- coding: utf-8 -*-
"""fixB: разведка данных (только чтение): виды номеров, источники, роли, адреса, поиск.
Номера в выводе замаскированы (цифры -> x), кроме длины."""
import io
import json
import os
import re
import sqlite3
from collections import Counter

K = r'C:\centro2\data\meyer_baza1.db'
S = r'C:\centro2\data\centro_sales_meyer1.db'
D = r'C:\seostat\drop\drop-storage'
c = sqlite3.connect('file:%s?mode=ro' % K, uri=True)
c.row_factory = sqlite3.Row
out = {}
kol = [r[1] for r in c.execute('pragma table_info(contact)')]
out['contact_kolonki'] = kol
for pole in ('phone_type', 'role', 'source', 'nomer_ne_lichnyy', 'kind'):
    if pole in kol:
        out['contact_' + pole] = Counter(str(r[0])[:60] for r in c.execute('select %s from contact' % pole)).most_common(40)
out['person_kolonki'] = [r[1] for r in c.execute('pragma table_info(person)')]
kc = [r[1] for r in c.execute('pragma table_info(company)')]
out['company_kolonki'] = kc


def maska(s):
    return re.sub(r'\d', 'x', str(s or ''))


prim = []
for r in c.execute('select * from company limit 5'):
    d = dict(r)
    prim.append({k: maska(d.get(k))[:200] for k in ('search_blob', 'adres', 'region', 'region_ishodnyy',
                                                     'telefony_predpriyatiya', 'telefony_iz_bazy',
                                                     'nomera_bez_vladelca', 'telefony_checko', 'lpr_kratko',
                                                     'lpr_roli', 'chas_poyas', 'bazy', 'direktor') if k in d})
out['company_primery'] = prim
# сколько адресов/регионов/поясов заполнено
out['zapolneno'] = {k: c.execute("select count(*) from company where coalesce(%s,'')<>''" % k).fetchone()[0]
                    for k in ('adres', 'region', 'region_ishodnyy', 'chas_poyas', 'telefony_predpriyatiya',
                              'telefony_iz_bazy', 'nomera_bez_vladelca', 'telefony_checko', 'search_blob')
                    if k in kc}
# есть ли адрес в search_blob
n = m = 0
for r in c.execute('select search_blob, adres from company'):
    if r['adres']:
        n += 1
        gorod = re.findall(r'(?:г\.?|город)\s*([А-ЯЁ][а-яё\-]+)', r['adres'])
        if gorod and gorod[0].lower() in (r['search_blob'] or '').lower():
            m += 1
out['gorod_v_blob'] = [m, n]
# телефоны в blob?
n = m = 0
for r in c.execute("select c.inn, c.search_blob, k.value from company c join contact k on k.inn=c.inn and k.kind='phone' limit 400"):
    n += 1
    d = re.sub(r'\D', '', r['value'] or '')[-10:]
    if d and d in re.sub(r'\D', '', r['search_blob'] or ''):
        m += 1
out['telefon_v_blob_cifry'] = [m, n]
out['bazy'] = Counter(str(r[0]) for r in c.execute('select bazy from company')).most_common(20)
c.close()
s = sqlite3.connect('file:%s?mode=ro' % S, uri=True)
out['users'] = [list(r) for r in s.execute('select id, username, role, is_active, fio from users')]
out['sales_kolonki'] = {t: [r[1] for r in s.execute('pragma table_info(%s)' % t)]
                        for t in ('company_state', 'company_comment', 'activity_log')}
out['sales_schet'] = {t: s.execute('select count(*) from %s' % t).fetchone()[0]
                      for t in ('company_state', 'company_comment', 'activity_log', 'company_assignment')}
out['journal_mode'] = s.execute('pragma journal_mode').fetchone()[0]
out['tablicy'] = [r[0] for r in s.execute("select name from sqlite_master where type='table'")]
s.close()
io.open(os.path.join(D, 'fixB-probe.json'), 'w', encoding='utf-8').write(json.dumps(out, ensure_ascii=False, indent=1))
print('ok', len(json.dumps(out)))
print(json.dumps({k: out[k] for k in ('users', 'sales_schet', 'journal_mode', 'zapolneno', 'gorod_v_blob', 'telefon_v_blob_cifry')}, ensure_ascii=False))
print('замок:', os.path.exists(r'C:\centro2\_zamok.txt'))
