# -*- coding: utf-8 -*-
"""Достроить КАРТОЧКУ извещения из реестрового номера: 1-я сессия права, поиск не привязывает.

Её замер глазами уточнил наш спор о метке ссылок, и уточнение важнее самого спора:

    поиск по реестровому номеру (`?searchString=0373…`) доказывает, что ЛОТ СУЩЕСТВУЕТ,
    но ИНН предприятия на этой странице НЕТ — привязка не доказана;
    карточка (`/ea44/view/common-info?regNumber=…`) ИНН печатает.

Раньше я записала «прямой путь к карточке 404-ит на всех 20» — и это было верно для той
формы пути, которую я тогда пробовала. Значит надо не спорить, а найти рабочую форму для
каждого типа процедуры: у 44-ФЗ и 223-ФЗ пути разные.

Проверяю ШЕСТЬ форм на живых номерах из моего же потока и меряю не код ответа, а
НАЛИЧИЕ ИНН предприятия в теле. Плюс отрицательный контроль: заведомо несуществующий номер
той же длины — если по нему «карточка откроется с ИНН», мерке грош цена.

Числа в КОНЦЕ.
"""
import collections, io, json, os, re, ssl, urllib.request
OPS = r'C:\sender\_ops'
POTOK = os.path.join(OPS, 'park_ingest_3d.jsonl')
FORMY = ['https://zakupki.gov.ru/epz/order/notice/ea44/view/common-info.html?regNumber=%s',
         'https://zakupki.gov.ru/epz/order/notice/ea20/view/common-info.html?regNumber=%s',
         'https://zakupki.gov.ru/epz/order/notice/ok504/view/common-info.html?regNumber=%s',
         'https://zakupki.gov.ru/epz/order/notice/inforeq/view/common-info.html?regNumber=%s',
         'https://zakupki.gov.ru/epz/order/notice/zk504/view/common-info.html?regNumber=%s',
         'https://zakupki.gov.ru/epz/order/notice/rpec/view/common-info.html?regNumber=%s']
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0.0.0 Safari/537.36')
ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
net = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                  urllib.request.ProxyHandler({}))
TEG = re.compile(r'<[^>]+>')
NOMER = re.compile(r'searchString=(\d{11,25})')

pary = []
for s in io.open(POTOK, encoding='utf-8'):
    try:
        o = json.loads(s)
    except Exception:
        continue
    m = NOMER.search(str(o.get('istochniki') or ''))
    if m and o.get('inn'):
        pary.append((o['inn'], m.group(1)))
    if len(pary) >= 12:
        break
pary.append(('7707083893', '0173100007519000999'))   # ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ: номера нет

sch = collections.Counter(); rabochie = collections.Counter(); primery = []
for inn, nom in pary:
    kontrol = nom == '0173100007519000999'
    nashli = ''
    for f in FORMY:
        u = f % nom
        try:
            with net.open(urllib.request.Request(u, headers={'User-Agent': UA,
                                                             'Accept-Language': 'ru'}),
                          timeout=40) as rs:
                t = re.sub(r'\s+', ' ', TEG.sub(' ', rs.read(400000).decode('utf-8', 'replace')))
        except Exception:
            continue
        if inn in re.sub(r'\D', '', t):
            nashli = u
            rabochie[f.split('/notice/')[1].split('/')[0]] += 1
            break
    if kontrol:
        sch['КОНТРОЛЬ ПРОБИТ' if nashli else 'контроль чист: по выдуманному номеру ИНН не нашёлся'] += 1
        continue
    sch['карточка найдена, ИНН на ней есть' if nashli else 'ни одна форма не дала ИНН'] += 1
    if nashli and len(primery) < 6:
        primery.append((inn, nashli[:96]))

print('\n\n########## ЧТО ОТКРЫЛОСЬ')
for p in primery:
    print('  %-12s %s' % p)
print('\n########## ЧИСЛА')
print('  пар «ИНН + реестровый номер» проверено %3d' % (len(pary) - 1))
for k, v in sch.most_common():
    print('     %-52s %3d' % (k[:52], v))
print('  --- какая форма сработала')
for k, v in rabochie.most_common():
    print('     %-20s %3d' % (k, v))
print('ИТОГ ' + json.dumps(dict(sch), ensure_ascii=False))
