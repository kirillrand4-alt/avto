# -*- coding: utf-8 -*-
"""Почему компаний из файла другой сессии нет в моей базе; выгрузка tehlpr.db на дроп."""
import csv
import io
import json
import os
import re
import shutil
import sqlite3

ИНН = json.loads(r'''["1106018296", "1215233310", "1650032058", "1650307217", "1650410870", "1657200174", "1661069243", "1831189149", "2124009521", "2308001057", "2312008947", "2312143777", "2320227766", "2325012387", "2352034598", "2370004204", "2465164164", "2721243532", "2902038052", "3100026209", "3123362207", "3329055175", "4202023230", "4205281286", "4345000224", "4345415959", "4401185966", "4705068774", "5010047857", "5024194587", "5053034860", "5256128930", "5407972390", "5452114972", "5501092820", "5504215847", "5610253957", "5644023870", "5751055570", "5829002496", "5902037103", "5905999363", "5920038082", "6141044001", "6230094702", "6318072216", "6321297643", "6449070854", "6501160052", "6657004027", "6658519646", "6659043053", "6670493070", "6679096134", "6686071814", "6827021061", "7325078852", "7415001607", "7447278810", "7704694125", "7707405685", "7709961550", "7710654988", "7721381193", "7801447185", "7806191794", "7810724847", "7817054648", "8619007581", "8620013533", "9102016849", "9102210229", "9103094582", "9200007507", "9704210635"]''')
СЕГМЕНТЫ = [('2', ('01.64', '01.11', '01.13.52', '01.25.2')), ('3', ('10.',)),
            ('4', ('52.10.3', '01.63', '10.61')), ('5', ('10.39.2', '01.25.3')),
            ('6', ('01.25.1', '10.39.2', '10.32'))]


def коды(*строки):
    вс = []
    for s in строки:
        for к in re.findall(r'\d{2}(?:\.\d{1,2}){0,3}', s or ''):
            if к not in вс:
                вс.append(к)
    return вс


def попадает(вс, префиксы):
    for к in вс:
        for п in префиксы:
            if (п.endswith('.') and к.startswith(п)) or к == п or к.startswith(п + '.'):
                return True
    return False


o = {'всего': len(ИНН), 'нет_нигде': 0, 'по_правилу_попадает': [], 'подстрока_10': 0, 'примеры': []}
c = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True, timeout=60)
c.execute(r"attach database 'file:C:\sender\obzvon-index.db?mode=ro' as obz")
for и in ИНН:
    р = c.execute("select coalesce(c.okved,''), coalesce(c.okved_all,''), coalesce(c.is_competitor,0), "
                  "coalesce(c.status_egrul,''), c.name from companies c where c.inn=?", (и,)).fetchone()
    q = c.execute("select coalesce(okved_main,''), coalesce(okved_all_codes,''), status, name_short "
                  "from obz.obzvon where inn=?", (и,)).fetchone()
    if not р and not q:
        o['нет_нигде'] += 1
        continue
    все = коды(*(list(р[:2]) if р else []) + (list(q[:2]) if q else []))
    сегм = [с for с, п in СЕГМЕНТЫ if попадает(все, п)]
    сырое = ' '.join((р[1] if р else '') + ' ' + (q[1] if q else ''))
    if сегм:
        o['по_правилу_попадает'].append([и, сегм, р[2] if р else '', (р[3] if р else '') or (q[2] if q else '')])
    elif re.search(r'10\.\d', сырое):
        o['подстрока_10'] += 1
    if len(o['примеры']) < 12:
        o['примеры'].append([и, (р[4] if р else q[3])[:30], (р[0] if р else q[0])[:40],
                             [к for к in все if '10' in к][:6]])

# tehlpr целиком — на дроп (3,7 тыс. строк)
t = sqlite3.connect(r'file:C:\sender\tehlpr.db?mode=ro', uri=True, timeout=60)
кол = [r[1] for r in t.execute('pragma table_info(tehlpr)')]
п = r'C:\sender\server\tehlpr-dump.csv'
with io.open(п, 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f, delimiter=';')
    w.writerow(кол)
    for r in t.execute('select * from tehlpr'):
        w.writerow(r)
    f.flush()
    os.fsync(f.fileno())
shutil.copyfile(п, r'C:\seostat\drop\drop-storage\tehlpr-dump.csv')
o['tehlpr_с_телефоном'] = t.execute("select count(*), sum(lichnyy_mobilnyy in (1,'1')) from tehlpr "
                                    "where coalesce(phone,'')<>''").fetchone()
t.close()
c.close()
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, default=str))
