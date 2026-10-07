# -*- coding: utf-8 -*-
r"""ОКВЭД и выручка для базы CC (владелец 07.10) без checko (сервер в 429 у checko):
  * DaData findById — основной ОКВЭД, регион, статус, наименование (доп. ОКВЭД наш тариф не даёт);
  * открытые данные ФНС revexp (C:\sender\_ops\ak\fns\revexp.zip, «Сведения о суммах доходов и
    расходов», ДатаСост 31.12.2025) — доход и расход 2025 по ИНН (так же «Доход 2025» в таблице CC);
  * доп. ОКВЭД — что уже есть у нас: stage_log 'checko' (all=…), companies.okved_all, obzvon.
Вход: C:\seostat\drop\drop-storage\cc-inn-dlya-checko.txt. Выход: cc-fns.json (сервер + дроп).
"""
import io
import json
import os
import re
import shutil
import sqlite3
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402  (_read_secret)

ИНН = [s.strip() for s in io.open(r'C:\seostat\drop\drop-storage\cc-inn-dlya-checko.txt', encoding='utf-8') if s.strip()]
нужны = set(ИНН)
out = {i: {} for i in ИНН}
_прямой = urllib.request.build_opener(urllib.request.ProxyHandler({}))
tok = EC._read_secret('DADATA_TOKEN')
for i in ИНН:
    try:
        body = json.dumps({'query': i}).encode()
        req = urllib.request.Request('https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party',
                                     data=body, method='POST', headers={
                                         'Content-Type': 'application/json', 'Accept': 'application/json',
                                         'Authorization': 'Token ' + tok})
        с = json.loads(_прямой.open(req, timeout=30).read()).get('suggestions') or []
        if с:
            d = с[0]['data']
            а = (d.get('address') or {})
            out[i].update({'название': (d.get('name') or {}).get('short_with_opf') or с[0].get('value'),
                           'оквэд_осн': d.get('okved') or '',
                           'регион': ((а.get('data') or {}).get('region_with_type') or ''),
                           'город': ((а.get('data') or {}).get('city') or ''),
                           'статус': ((d.get('state') or {}).get('status') or ''),
                           'огрн': d.get('ogrn') or ''})
    except Exception as e:  # noqa: BLE001
        out[i]['dadata_ошибка'] = repr(e)[:80]
    time.sleep(0.05)

z = zipfile.ZipFile(r'C:\sender\_ops\ak\fns\revexp.zip')
найдено = 0
for zi in z.infolist():
    if not zi.filename.lower().endswith('.xml'):
        continue
    with z.open(zi) as fh:
        for ev, el in ET.iterparse(fh, events=('end',)):
            if not el.tag.endswith('Документ'):
                continue
            inn = доход = расход = None
            for ch in el:
                if 'СведНП' in ch.tag:
                    inn = ch.get('ИННЮЛ') or ch.get('ИННФЛ')
                elif 'ДохРасх' in ch.tag:
                    доход, расход = ch.get('СумДоход'), ch.get('СумРасход')
            if inn in нужны:
                out[inn].update({'доход': float(доход or 0), 'расход': float(расход or 0),
                                 'доход_год': (el.get('ДатаСост') or '')[-4:]})
                найдено += 1
            el.clear()

c = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True, timeout=120)
c.execute(r"attach database 'file:C:\sender\obzvon-index.db?mode=ro' as obz")
for i in ИНН:
    коды = []
    for (д,) in c.execute("select detail from stage_log where inn=? and stage='checko' and detail like '%all=%'", (i,)):
        м = re.search(r'all=([\d.,]+)', д or '')
        if м:
            коды += м.group(1).split(',')
    for (s,) in c.execute("select coalesce(okved_all,'') from companies where inn=? union all "
                          "select coalesce(okved_all_codes,'') from obz.obzvon where inn=?", (i, i)):
        коды += re.findall(r'\d{2}(?:\.\d{1,2}){0,3}', s)
    out[i]['оквэд_все'] = list(dict.fromkeys(к for к in коды if к))
c.close()

п = r'C:\sender\server\cc-fns.json'
with io.open(п, 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False)
    f.flush()
    os.fsync(f.fileno())
shutil.copyfile(п, r'C:\seostat\drop\drop-storage\cc-fns.json')
print('===ИТОГ===')
print(json.dumps({'инн': len(ИНН), 'dadata_оквэд': sum(1 for v in out.values() if v.get('оквэд_осн')),
                  'доход_2025': найдено, 'доп_оквэд_есть': sum(1 for v in out.values() if len(v.get('оквэд_все', [])) > 1),
                  'ошибки_dadata': sum(1 for v in out.values() if v.get('dadata_ошибка'))}, ensure_ascii=False))
