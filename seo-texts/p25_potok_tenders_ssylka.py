# -*- coding: utf-8 -*-
"""41 750 строк tenders МОЖНО доказать: у них есть реестровый номер. Мой прежний ноль был неполон.

Что я записала в журнал час назад: «41 751 строку доказать нечем, ни ссылки, ни номера
документа». Первая половина верна, вторая — нет, и ошибка была в том, ЧТО я считала номером.
Я искала номер заключения ЭПБ вида «42-ТУ-896427-2026» и, не найдя его, объявила строку
безнадёжной. А колонки говорят другое:

    строк без ссылки 41 751 | platform 41 751 | reg_number 41 750 | inn 38 853
    org 39 672 | phone 2 603 | email 2 590 | fio 1 833

`reg_number` заполнен практически везде: `0373100048525000087`, `32616228544`. Это реестровый
номер извещения ЕИС, и адрес из него строится прямо. Урок себе прежний и уже оплаченный:
СНАЧАЛА СМОТРЕТЬ КОЛОНКИ, потом объявлять ноль. Ноль — диагноз, и диагноз бывает неверным.

ПОРЯДОК ТОТ ЖЕ, ЧТО И С ЭПБ, И ОН НЕ ОБСУЖДАЕТСЯ. Собранная ссылка — гипотеза. Сначала
открываю двадцать случайных с сервера и смотрю три вещи: открылась ли, стоит ли на странице
ИНН предприятия, стоит ли название закупки. Только при высокой доле пишу поток, и каждая
строка несёт пометку «ссылка собрана из реестрового номера, проверено N из 20». Если доля
низкая — файл не пишется вовсе, и это будет честнее сорока тысяч красивых строк.

Машину в этих строках доказывает `title` («Закупка. Запчасти компрессора (Атлас Копко)»),
поэтому вид машины беру из него теми же словарями, что и в первом потоке, и строку без
названной машины в поток не пускаю.

Только чтение. Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import random
import re
import sqlite3
import ssl
import urllib.request

BAZA = r'C:\seostat\drop\drop-storage\atlas_copco.db'
VYHOD = r'C:\sender\_ops\park_ingest_3b.jsonl'
PROVERIT = 20
POROG = 0.5

VID = (('воздуходувка', re.compile(r'воздуходув|газодув', re.I)),
       ('нагнетатель', re.compile(r'нагнетател', re.I)),
       ('ВРУ', re.compile(r'воздухоразделен|\bВРУ\b|криоген', re.I)),
       ('генератор азота', re.compile(r'генератор\w*\s+азота|азотн\w+\s+станци|'
                                      r'мембранн\w+\s+азот|азотн\w+\s+установк', re.I)),
       ('генератор кислорода', re.compile(r'генератор\w*\s+кислорода|кислородн\w+\s+станци|'
                                          r'концентратор\w*\s+кислорода|кислородн\w+\s+установк', re.I)),
       ('МКС / передвижная', re.compile(r'\bМКС\b|передвижн\w+\s+компрессор|'
                                        r'мобильн\w+\s+компрессор|дизельн\w+\s+компрессор', re.I)),
       ('осушитель', re.compile(r'осушител', re.I)),
       ('ГПА', re.compile(r'газоперекачивающ|\bГПА\b', re.I)),
       ('компрессор', re.compile(r'компрессор', re.I)))
PRINCIP = (('центробежный', re.compile(r'центробежн|турбокомпрессор', re.I)),
           ('винтовой', re.compile(r'винтов', re.I)),
           ('поршневой', re.compile(r'поршнев', re.I)))
CHUZH = re.compile(r'вентилятор|дымосос|\bнасос\w*\b|градирн|кондиционер|автотранспорт', re.I)
KLASS = {'ГПА': 5, 'компрессор': 4, 'нагнетатель': 4, 'ВРУ': 4, 'генератор азота': 4,
         'генератор кислорода': 4, 'воздуходувка': 3, 'МКС / передвижная': 3, 'осушитель': 2}
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0.0.0 Safari/537.36')
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
net = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                  urllib.request.ProxyHandler({}))
TEG = re.compile(r'<[^>]+>')


def adres(platforma, nomer):
    n = str(nomer or '').strip()
    if not n.isdigit():
        return ''
    if (platforma or '').lower() == 'eis':
        return ('https://zakupki.gov.ru/epz/order/notice/notice-info/common-info.html'
                '?regNumber=' + n)
    return ''


cx = sqlite3.connect('file:%s?mode=ro' % BAZA.replace('\\', '/'), uri=True)
kol = [r[1] for r in cx.execute('pragma table_info("tenders")')]
zapisi = {}
prichiny = collections.Counter()
for r in cx.execute('select %s from tenders' % ','.join('"%s"' % k for k in kol)):
    d = dict(zip(kol, r))
    stroka = ' '.join(str(v) for v in r if v is not None)
    if re.search(r'https?://', stroka):
        continue                       # эти уже ушли первым потоком
    inn = str(d.get('inn') or '').strip()
    if not inn.isdigit():
        prichiny['ИНН нет'] += 1
        continue
    u = adres(d.get('platform'), d.get('reg_number'))
    if not u:
        prichiny['площадка не ЕИС либо номер не цифровой — адрес не строю'] += 1
        continue
    nazv = str(d.get('title') or '')
    if CHUZH.search(nazv):
        prichiny['чужая машина в названии закупки'] += 1
        continue
    vid = next((i for i, rg in VID if rg.search(nazv)), '')
    if not vid:
        prichiny['машина в названии закупки не названа'] += 1
        continue
    k = (inn, u)
    z = zapisi.setdefault(k, {'vid': collections.Counter(), 'nazv': set(), 'org': '',
                              'p': collections.Counter(), 'zapros': set(),
                              'fio': set(), 'tel': set(), 'pochta': set()})
    z['vid'][vid] += 1
    z['nazv'].add(re.sub(r'\s+', ' ', nazv)[:200])
    z['org'] = z['org'] or str(d.get('org') or '')[:150]
    for i, rg in PRINCIP:
        if rg.search(nazv):
            z['p'][i] += 1
            break
    if d.get('query'):
        z['zapros'].add(str(d['query'])[:40])
    for pole, kuda in (('fio', 'fio'), ('phone', 'tel'), ('email', 'pochta')):
        v = str(d.get(pole) or '').strip()
        if v:
            z[kuda].add(v[:60])
cx.close()

kand = list(zapisi.items())
random.seed(3311)
obrazcy = random.sample(kand, min(PROVERIT, len(kand))) if kand else []
proverka, horosho = [], 0
for (inn, u), z in obrazcy:
    try:
        rq = urllib.request.Request(u, headers={'User-Agent': UA, 'Accept-Language': 'ru'})
        with net.open(rq, timeout=60) as rs:
            kod = rs.getcode()
            telo = rs.read(500000).decode('utf-8', 'replace')
        text = re.sub(r'\s+', ' ', TEG.sub(' ', telo))
        est_inn = inn in re.sub(r'\D', '', text)
        slova = [w for w in re.findall(r'[А-Яа-я]{6,}', list(z['nazv'])[0])][:3]
        est_nazv = any(w.lower()[:6] in text.lower() for w in slova)
        if est_inn and est_nazv:
            v = 'ДОКАЗЫВАЕТ: ИНН и название закупки на странице'
            horosho += 1
        elif est_inn:
            v = 'открылась, ИНН есть, названия закупки нет'
            horosho += 1
        else:
            v = 'открылась, но ИНН предприятия на ней нет'
    except Exception as e:  # noqa: BLE001
        kod, v = 0, 'не открылась: %s' % str(e)[:50]
    proverka.append((inn, kod, v, u))

dolya = horosho / float(len(proverka)) if proverka else 0.0
potok = []
if dolya >= POROG:
    for (inn, u), z in kand:
        vid = z['vid'].most_common(1)[0][0]
        potok.append({
            'inn': inn, 'vid': vid,
            'princip': (z['p'].most_common(1) or [('не установлен', 0)])[0][0],
            'vetka': 'закупка (ЕИС, выгрузка atlas_copco)',
            'klass_ceny': KLASS.get(vid, 2),
            'nazvanie_zakupki': ' | '.join(sorted(z['nazv'])[:2]),
            'organizaciya': z['org'],
            'zapros_kotorym_nashli': ' | '.join(sorted(z['zapros'])[:2]),
            'istochniki': u, 'istochnikov': 1,
            'ssylka_otkuda': 'собрана из реестрового номера ЕИС, проверено %d из %d'
                             % (horosho, len(proverka)),
            'chelovek': ' | '.join(sorted(z['fio'])[:2]),
            'telefon': ' | '.join(sorted(z['tel'])[:2]),
            'pochta': ' | '.join(sorted(z['pochta'])[:2]),
            'kto': '3-я сессия, park_ingest_3b (закупки со ссылкой из номера)',
        })
    with io.open(VYHOD, 'w', encoding='utf-8') as f:
        for o in potok:
            f.write(json.dumps(o, ensure_ascii=False) + '\n')

vylozheno = 'поток не писала — доля доказавших ниже порога'
if potok:
    try:
        op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        rq = urllib.request.Request('%s/%s' % (os.environ.get('DROP_URL', '').rstrip('/'),
                                               os.path.basename(VYHOD)),
                                    data=io.open(VYHOD, 'rb').read(), method='PUT',
                                    headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
        vylozheno = op.open(rq, timeout=300).read().decode('utf-8', 'replace')[:110]
    except Exception as e:  # noqa: BLE001
        vylozheno = 'не выложено: %s' % str(e)[:90]

print('\n\n########## ДВАДЦАТЬ СОБРАННЫХ ССЫЛОК, ОТКРЫТЫХ С СЕРВЕРА')
for inn, kod, v, u in proverka:
    print('  %-13s http %-4s %s' % (inn, kod, v))
    print('        %s' % u[:120])
print('\n########## ЧИСЛА')
print('  кандидатов (ИНН + адрес)      %7d' % len(kand))
print('  разных ИНН среди кандидатов   %7d' % len({i for i, _ in zapisi}))
print('  проверено ссылок              %7d, доказали %d, доля %.2f (порог %.2f)'
      % (len(proverka), horosho, dolya, POROG))
print('  записей в потоке              %7d' % len(potok))
print('  разных ИНН в потоке           %7d' % len({o['inn'] for o in potok}))
print('  из них с человеком в строке   %7d' % sum(1 for o in potok if o['chelovek']))
print('  --- по виду машины')
for k, v in collections.Counter(o['vid'] for o in potok).most_common():
    print('     %-26s %7d' % (k, v))
print('  --- почему не взяты остальные')
for k, v in prichiny.most_common(8):
    print('     %-52s %7d' % (k[:52], v))
print('  выложено: %s' % vylozheno)
print('ИТОГ ' + json.dumps({'кандидатов': len(kand), 'доказали из 20': horosho,
                            'записей': len(potok),
                            'ИНН': len({o['inn'] for o in potok})}, ensure_ascii=False))
