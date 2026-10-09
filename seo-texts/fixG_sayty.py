# -*- coding: utf-8 -*-
"""fixG (локально): сайты кандидатов на замену – скачать и проверить «чей сайт» методом агента D.

1. Временный каталог кандидатов (sqlite в схеме, которую читает fixD_chey_sayt.py): компания (ИНН,
   название, сайт, юрадрес и регион из checko) и её номера из файла 3 (источник, фрагмент).
2. Страницы – тем же скачивателем, что у D (fixD_kachat.py: по одному запросу на домен за раз,
   пауза, кэш): все страницы-источники номеров (кроме площадок/агрегаторов) + главная сайта;
   затем до 5 страниц «контакты/реквизиты/о компании» по ссылкам и второй проход D
   (политика/оферта/реквизиты по ссылкам + угаданные пути, до 10 на домен) – у всех доменов,
   потому что ИНН/ОГРН чаще всего стоит в подвале, политике или реквизитах.
3. fixD_chey_sayt.py по этим страницам: свой (ИНН/ОГРН на сайте; руководитель или юрадрес из checko),
   группа, чужой, не определено.

    python3 -I fixG_sayty.py <kandidaty.json> <checko-razbor.json> <svyazi.json> <папка-страниц> <выход-chey.json> [первых N]
"""
import json
import os
import re
import sqlite3
import subprocess
import sys

KAND, RAZBOR, SVYAZI, PAPKA, VYHOD = sys.argv[1:6]
N = int(sys.argv[6]) if len(sys.argv) > 6 else 45
ZDES = os.path.dirname(os.path.abspath(__file__))
kand = json.load(open(KAND, encoding='utf-8'))[:N]
razbor = json.load(open(RAZBOR, encoding='utf-8'))
os.makedirs(PAPKA, exist_ok=True)
BAZA = os.path.join(os.path.dirname(os.path.abspath(VYHOD)), 'kandidaty.db')
if os.path.exists(BAZA):
    os.remove(BAZA)
k = sqlite3.connect(BAZA)
k.execute('create table company (inn text, predpriyatie text, bazy text, sayt text, sayt_chey text, adres text, region text)')
k.execute('create table contact (id integer primary key, inn text, value text, kind text, person text, role text, position text, '
          'source text, source_url text, nomer_ne_lichnyy text, fragment text)')
for c in kand:
    z = razbor.get(c['inn']) or {}
    k.execute('insert into company values (?,?,?,?,?,?,?)', (c['inn'], c['nazvanie'], 'кандидат', c['sayt'], c['svyazka'],
                                                            z.get('adres') or '', c['region']))
    for x in c['nomera']:
        k.execute('insert into contact (inn, value, kind, person, role, position, source, source_url, nomer_ne_lichnyy, fragment) '
                  'values (?,?,?,?,?,?,?,?,?,?)', (c['inn'], x['nomer'], 'phone', None, x['podpis'], '',
                                                   ' · '.join(v for v in (x['istochnik'], x['chya']) if v), x['url'], None,
                                                   x['fragment'][:400]))
k.commit()
k.close()
print('временный каталог кандидатов: %d компаний -> %s' % (len(kand), BAZA))

# 2. скачать – скачивателем агента D (модуль читает аргументы при импорте)
sys.argv = [os.path.join(ZDES, 'fixD_kachat.py'), BAZA, PAPKA, '--potokov', '12']
sys.path.insert(0, ZDES)
import fixD_kachat as K  # noqa: E402

K.glavnaya()
domeny = set()
kk = sqlite3.connect(BAZA)
for (s,) in kk.execute('select sayt from company'):
    for x in re.split(r'[\s,;]+', s or ''):
        if K.domen(x) and not K.ne_sayt(K.domen(x)):
            domeny.add(K.domen(x))
for (u,) in kk.execute('select source_url from contact'):
    for x in (u or '').replace(';', ' ').split():
        if x.startswith('http') and K.domen(x) and not K.ne_sayt(K.domen(x)):
            domeny.add(K.domen(x))
K.dobavka(sorted(domeny))

# 3. «чей сайт» – разбор агента D как есть
r = subprocess.run([sys.executable, '-I', os.path.join(ZDES, 'fixD_chey_sayt.py'), BAZA, PAPKA, SVYAZI, RAZBOR, VYHOD],
                   capture_output=True, text=True)
print(r.stdout[-3000:], r.stderr[-3000:])
