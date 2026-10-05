# -*- coding: utf-8 -*-
"""Прикидка объёма мейеровской базы по сегментам из того, что уже собрано."""
import json
import re
import sqlite3

СЕГМЕНТЫ = {
    '2 семеноводы': ('01.64', '01.11', '01.13.52', '01.25.2'),
    '3 пищевые': ('10.',),
    '4 элеваторы': ('52.10.3', '01.63', '10.61'),
    '5 орехи': ('10.39.2', '01.25.3'),
    '6 ягоды': ('01.25.1', '10.39.2', '10.32'),
    '7 доп. ОКВЭД (наше предложение)': ('46.21', '01.26', '01.61', '46.31', '46.37'),
}
ЭКСПОРТ = re.compile(r'экспорт|внешнеэконом|\bВЭД\b|export', re.I)
ТОВАР = re.compile(r'зерн|пшениц|ячмен|кукуруз|бобов|горох|нут|чечевиц|соя|сои|масличн|'
                   r'подсолнеч|рапс|лён|льн|семен|орех|ягод|крупа|круп|мука|солод', re.I)


def коды(*строки):
    вс = set()
    for s in строки:
        for к in re.findall(r'\d{2}(?:\.\d{1,2}){0,3}', s or ''):
            вс.add(к)
    return вс


def попадает(вс, префиксы):
    for к in вс:
        for п in префиксы:
            if п.endswith('.'):
                if к.startswith(п):
                    return True
            elif к == п or к.startswith(п + '.'):
                return True
    return False


c = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True, timeout=60)
c.execute(r"attach database 'file:C:\sender\obzvon-index.db?mode=ro' as obz")
строки = c.execute(
    "select c.inn, coalesce(c.okved,''), coalesce(c.okved_all,''), "
    "coalesce(o.okved_main,''), coalesce(o.okved_all_codes,''), "
    "coalesce(c.site_description,'')||' '||coalesce(c.activity,''), "
    "coalesce(c.region,''), coalesce(c.status_egrul,''), coalesce(c.is_competitor,0) "
    'from companies c left join obz.obzvon o on o.inn=c.inn').fetchall()
# компании из обзвон-базы, которых нет в companies
доп = c.execute(
    "select o.inn, '', '', coalesce(o.okved_main,''), coalesce(o.okved_all_codes,''), '', "
    "coalesce(o.region,''), coalesce(o.status,''), 0 from obz.obzvon o "
    'where not exists (select 1 from companies c where c.inn=o.inn)').fetchall()

итог = {сег: 0 for сег in СЕГМЕНТЫ}
итог['1 экспортёры (по тексту)'] = 0
инн_в_базе = set()
бел = 0
ликв = 0
for (inn, ok, oka, om, omall, текст, рег, статус, конк) in строки + доп:
    if 'беларус' in (рег or '').lower() or len(str(inn)) == 9:
        бел += 1
    вс = коды(ok, oka, om, omall)
    попал = False
    for сег, пр in СЕГМЕНТЫ.items():
        if попадает(вс, пр):
            итог[сег] += 1
            попал = True
    if ЭКСПОРТ.search(текст) and ТОВАР.search(текст):
        итог['1 экспортёры (по тексту)'] += 1
        попал = True
    if попал:
        инн_в_базе.add(str(inn))
        if 'ликвид' in (статус or '').lower():
            ликв += 1

# контакты по отобранным
спис = list(инн_в_базе)
def счёт(sql):
    n = 0
    for i in range(0, len(спис), 800):
        к = спис[i:i + 800]
        n += c.execute(sql % ','.join('?' * len(к)), к).fetchone()[0]
    return n

контакты = {
    'компаний_всего_уник': len(спис),
    'из_них_ликвидировано': ликв,
    'с_именным_ЛПР_people': счёт('select count(distinct inn) from people where inn in (%s)'),
    'с_именным_imena': счёт('select count(distinct inn) from imena where inn in (%s)'),
    'с_почтой': счёт('select count(distinct inn) from emails where inn in (%s)'),
    'с_телефоном': счёт('select count(distinct inn) from phone_contacts where inn in (%s)'),
    'с_выручкой': счёт("select count(*) from companies where inn in (%s) and coalesce(revenue_rub,0)>0"),
    'с_сайтом': счёт("select count(*) from companies where inn in (%s) and coalesce(site,'')<>''"),
}
c.close()
print('===ИТОГ===')
print(json.dumps({'по_сегментам': итог, 'контакты': контакты, 'белорусских': бел},
                 ensure_ascii=False, indent=1))
