# -*- coding: utf-8 -*-
"""Кандидаты ЭТП ГПБ. Ссылку строю не на карточку, а на ПОИСК ПЛОЩАДКИ по её номеру.

Что выяснилось и почему прежний путь был закрыт:

    адрес карточки  /procedure/tender/etp/738892-postavka-turbokompressora-.../
    титул страницы  «ГП302295 Тендер на закупку Поставка турбокомпрессора воздушного…»

    в нашей таблице:  ГП302295 -> есть, 1 строка      738892 -> НЕТ ни одной
                      ГП219976 -> есть               657160 -> НЕТ
                      ГП124211 -> есть               573792 -> НЕТ

То есть в базе лежит РЕЕСТРОВЫЙ номер площадки, а адрес карточки требует ВНУТРЕННИЙ
идентификатор страницы, которого у нас нет вовсе. Построить адрес карточки из наших данных
нельзя в принципе — и это ответ на вопрос, почему `/procedures/etp/<номер>/` отдавал 200 на
любой мусор: он отдаёт заглушку с титулом «ЭТП ГПБ», что и показал контроль.

Зато поиск площадки по реестровому номеру работает: страница
`etpgpb.ru/procedures/?search=ГП302295` содержит и номер, и название закупки. Такую ссылку
и ставлю — с честной пометкой, что она ведёт на поиск, а не на карточку. Ровно как у ЕИС.

Здесь только сбор кандидатов: ИНН, номер, название, вид машины. Проверку браузером и запись
потока делает второй шаг — из песочницы, где живёт браузер раннера.

Только чтение. Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import re
import sqlite3
import urllib.request

BAZA = r'C:\seostat\drop\drop-storage\atlas_copco.db'
VYHOD = r'C:\sender\_ops\PARK-ETPGPB-KANDIDATY-3S.jsonl'
VID = (('воздуходувка', re.compile(r'воздуходув|газодув', re.I)),
       ('нагнетатель', re.compile(r'нагнетател', re.I)),
       ('ВРУ', re.compile(r'воздухоразделен|\bВРУ\b|криоген', re.I)),
       ('генератор азота', re.compile(r'генератор\w*\s+азота|азотн\w+\s+станци|азотн\w+\s+установк', re.I)),
       ('генератор кислорода', re.compile(r'генератор\w*\s+кислорода|кислородн\w+\s+станци|кислородн\w+\s+установк', re.I)),
       ('МКС / передвижная', re.compile(r'\bМКС\b|передвижн\w+\s+компрессор|мобильн\w+\s+компрессор', re.I)),
       ('осушитель', re.compile(r'осушител', re.I)),
       ('ГПА', re.compile(r'газоперекачивающ|\bГПА\b', re.I)),
       ('компрессор', re.compile(r'компрессор', re.I)))
CHUZH = re.compile(r'вентилятор|дымосос|\bнасос\w*\b|градирн|кондиционер|автотранспорт', re.I)
ZIP = re.compile(r'\bЗИП\b|запчаст|ремкомплект|сепаратор масла|фильтр|клапан|датчик|масло\b', re.I)

cx = sqlite3.connect('file:%s?mode=ro' % BAZA.replace('\\', '/'), uri=True)
kand, prichiny = {}, collections.Counter()
for inn, nom, tit, org in cx.execute(
        "select inn, reg_number, title, org from tenders where platform like 'etpgpb%'"):
    inn = str(inn or '').strip()
    nom = str(nom or '').strip()
    tit = str(tit or '')
    if not inn.isdigit():
        prichiny['ИНН нет'] += 1
        continue
    if not re.match(r'^[А-Я]{2}\d{4,8}$', nom):
        prichiny['номер не похож на реестровый номер площадки'] += 1
        continue
    if CHUZH.search(tit):
        prichiny['чужая машина в названии'] += 1
        continue
    vid = next((i for i, rg in VID if rg.search(tit)), '')
    if not vid:
        prichiny['машина в названии не названа'] += 1
        continue
    zip_li = bool(ZIP.search(tit))
    k = (inn, nom)
    if k in kand:
        continue
    kand[k] = {'inn': inn, 'nomer': nom, 'nazvanie': re.sub(r'\s+', ' ', tit)[:200],
               'organizaciya': str(org or '')[:140], 'vid': vid,
               'zip_ili_uslugi': zip_li,
               'ssylka': 'https://etpgpb.ru/procedures/?search=' + nom,
               'kto': '3-я сессия, кандидаты ЭТП ГПБ'}
cx.close()

with io.open(VYHOD, 'w', encoding='utf-8') as f:
    for o in kand.values():
        f.write(json.dumps(o, ensure_ascii=False) + '\n')
try:
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    rq = urllib.request.Request('%s/%s' % (os.environ.get('DROP_URL', '').rstrip('/'),
                                           os.path.basename(VYHOD)),
                                data=io.open(VYHOD, 'rb').read(), method='PUT',
                                headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
    vyl = op.open(rq, timeout=300).read().decode('utf-8', 'replace')[:110]
except Exception as e:  # noqa: BLE001
    vyl = 'не выложено: %s' % str(e)[:80]

mash = [o for o in kand.values() if not o['zip_ili_uslugi']]
print('\n\n########## ПРИМЕРЫ (сама машина, не ЗИП)')
for o in mash[:8]:
    print('  %-12s %-10s %-20s %s' % (o['inn'], o['nomer'], o['vid'][:20], o['nazvanie'][:70]))
print('\n########## ЧИСЛА')
print('  кандидатов                %6d  (разных ИНН %d)'
      % (len(kand), len({o['inn'] for o in kand.values()})))
print('  из них сама машина        %6d  (ИНН %d)'
      % (len(mash), len({o['inn'] for o in mash})))
print('  ЗИП, запчасти, услуги     %6d' % (len(kand) - len(mash)))
print('  --- по виду машины')
for k, v in collections.Counter(o['vid'] for o in kand.values()).most_common():
    print('     %-24s %6d' % (k, v))
print('  --- почему не взяты')
for k, v in prichiny.most_common(6):
    print('     %-52s %6d' % (k[:52], v))
print('  файл: %s' % VYHOD)
print('  выложено: %s' % vyl)
print('ИТОГ ' + json.dumps({'кандидатов': len(kand), 'сама машина': len(mash),
                            'ИНН': len({o['inn'] for o in kand.values()})}, ensure_ascii=False))
