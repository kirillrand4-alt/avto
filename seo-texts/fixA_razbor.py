# -*- coding: utf-8 -*-
"""Исправитель A: только ЧТЕНИЕ каталога Meyer — какие поля реально есть у контакта,
человека и компании (должность, вид номера, пояс, ЛПР, битрикс). Номера маскируются
(видны только первые 4 знака), на дроп — `fixA_razbor.json`.

    python3 zapusk_na_servere.py fixA_razbor.py
"""
import io
import json
import os
import re
import sqlite3

KAT = r'C:\centro2\data\meyer_baza1.db'
DROP = r'C:\seostat\drop\drop-storage'
INNY = ['7203319557', '6382000106', '5251001312', '3254002818', '1829013726', '2245002584']


def maska(v):
    s = str(v if v is not None else '')
    if re.search(r'\d{5,}', re.sub(r'[\s()\-+]', '', s)):
        return re.sub(r'\d', '0', s[:200])
    return s[:300]


k = sqlite3.connect('file:%s?mode=ro' % KAT, uri=True)
k.row_factory = sqlite3.Row
out = {}
for tab in ('contact', 'person', 'company'):
    out[tab + '_kolonki'] = [r[1] for r in k.execute('pragma table_info(%s)' % tab)]
out['contact'] = {}
out['person'] = {}
for inn in INNY:
    out['contact'][inn] = [{kk: maska(r[kk]) for kk in r.keys() if r[kk] not in (None, '', 0)}
                           for r in k.execute('select * from contact where inn=? limit 12', (inn,))]
    out['person'][inn] = [{kk: maska(r[kk]) for kk in r.keys() if r[kk] not in (None, '', 0)}
                          for r in k.execute('select * from person where inn=? limit 8', (inn,))]
pole = ['inn', 'region', 'chas_poyas', 'lpr_kratko', 'lpr_roli', 'lpr_mobilnyy', 'lpr_s_fio',
        'bitrix_kc', 'bitrix_kc_info', 'status_egrul', 'v_baze_obzvona', 'oborudovanie_po_okved',
        'moy_prioritet', 'popadanie']
est = [p for p in pole if p in out['company_kolonki']]
out['company'] = [dict(zip(est, [maska(x) for x in r]))
                  for r in k.execute('select %s from company order by rowid limit 40' % ','.join(est))]
out['company_bitrix'] = [dict(zip(est, [maska(x) for x in r]))
                         for r in k.execute("select %s from company where bitrix_kc_info like '%%СЦ%%' limit 10" % ','.join(est))] \
    if 'bitrix_kc_info' in est else []
out['schet'] = {}
for p in ('chas_poyas', 'status_egrul', 'v_baze_obzvona', 'oborudovanie_po_okved'):
    if p in out['company_kolonki']:
        out['schet'][p] = [list(r) for r in k.execute('select %s, count(*) from company group by 1 order by 2 desc limit 25' % p)]
cc = out['contact_kolonki']
for p in ('phone_type', 'nomer_ne_lichnyy', 'role', 'position', 'vid_nomera', 'chuzhoy_istochnik'):
    if p in cc:
        out['schet']['contact.' + p] = [list(r) for r in k.execute('select %s, count(*) from contact group by 1 order by 2 desc limit 40' % p)]
pc = out['person_kolonki']
# сколько номеров людей с добавочным в сырой записи
for p in ('phone', 'nomer_10cifr'):
    if p in pc:
        out['schet']['person.%s_dob' % p] = k.execute(
            "select count(*) from person where %s like '%%доб%%' or length(replace(replace(replace(replace(replace(%s,' ',''),'-',''),'(',''),')',''),'+',''))>11" % (p, p)).fetchone()[0]
        out['person_%s_obrazcy' % p] = [maska(r[0]) for r in k.execute(
            "select %s from person where %s like '%%доб%%' limit 8" % (p, p))]
io.open(os.path.join(DROP, 'fixA_razbor.json'), 'w', encoding='utf-8').write(
    json.dumps(out, ensure_ascii=False, indent=1))
print('ok', len(json.dumps(out)))
