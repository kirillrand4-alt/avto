# -*- coding: utf-8 -*-
"""ЕИС: достаю ЗАКАЗЧИКОВ, а не счётчик. Счётчик уже сказал, что там есть.

Предыдущий заход дал объёмы и, главное, доказал, чем можно пользоваться, а чем нельзя:

    okpd2IdsCodes=28.13.2  -> «более 41 000 000»   без фильтров вообще -> «более 41 000 000»
    searchString=компрессор -> 10 000              винтовой 819  поршневой 2 400
    генератор кислорода 2 200   кислородная станция 876   компрессорная станция 697
    воздуходувка 667   осушитель 536   генератор азота 272   ПКС 78   азотная станция 61

Заслон тогда прошёл: двенадцать слов дали двенадцать РАЗНЫХ чисел, значит поиск фильтрует,
а не показывает всё подряд. Код ОКПД2 как ключ отброшен доказательно — ЕИС его игнорирует.

Теперь беру не число, а строки. Из карточки выдачи мне нужны три вещи: номер извещения
(это и есть ссылка-доказательство), наименование заказчика и предмет закупки. ИНН в выдаче
не печатают — поэтому ИНН добываю сшивкой имени с боевой базой, и ЧЕСТНО ПОМЕЧАЮ, чей он:
«ИНН сшит по названию» это не то же самое, что «ИНН стоял в документе».

ДВА ЗАСЛОНА, оба обязательны:
1. Если разбор карточек дал ноль — печатаю кусок сырой разметки. Ноль это диагноз прибора,
   а не факт о ЕИС; без образца разметки чинить нечего.
2. Заказчик — не обязательно владелец машины. Слова «поставка», «монтаж», «ремонт» говорят
   о машине НА предприятии; но если в имени заказчика сидит «торг», «снаб», «сервис»,
   помечаю строку как подозрительную на посредника и НЕ выбрасываю — правило владельца
   «разделять, а не отсеивать».

Только чтение по сети. Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import re
import sqlite3
import ssl
import time
import urllib.parse
import urllib.request

SLOVA = ['компрессор', 'винтовой компрессор', 'поршневой компрессор', 'генератор азота',
         'генератор кислорода', 'азотная станция', 'кислородная станция',
         'передвижная компрессорная станция', 'осушитель сжатого воздуха',
         'воздухоразделительная установка', 'воздуходувка', 'компрессорная станция']
STRANIC = 4          # страниц на слово
NA_STRANICE = 50
BAZA = r'C:\sender\enrich.db'
VYHOD = r'C:\sender\_ops\PARK-EIS-ZAKAZCHIKI-3S.jsonl'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0.0.0 Safari/537.36')
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
op = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                 urllib.request.ProxyHandler({}))
REG = re.compile(r'regNumber=(\d{11,25})')
POSREDNIK = re.compile(r'торг|снаб|сервис|логист|поставк\w+\s+компани|трейд', re.I)


def tyanut(slovo, stranica):
    q = urllib.parse.urlencode({
        'searchString': slovo, 'morphology': 'on', 'pageNumber': stranica,
        'sortDirection': 'false', 'recordsPerPage': '_%d' % NA_STRANICE,
        'showLotsInfoHidden': 'false', 'sortBy': 'UPDATE_DATE',
        'fz44': 'on', 'fz223': 'on', 'af': 'on', 'ca': 'on', 'pc': 'on', 'pa': 'on'})
    u = 'https://zakupki.gov.ru/epz/order/extendedsearch/results.html?' + q
    r = urllib.request.Request(u, headers={'User-Agent': UA, 'Accept-Language': 'ru'})
    return u, op.open(r, timeout=90).read().decode('utf-8', 'replace')


def kartochki(html):
    """Режу выдачу по блокам записей и беру из каждого номер, заказчика и предмет."""
    out = []
    bloki = re.split(r'search-registry-entry-block|registry-entry__form', html)
    for b in bloki[1:]:
        m = REG.search(b)
        if not m:
            continue
        nomer = m.group(1)
        zak = ''
        mz = re.search(r'Заказчик[^<]*</div>\s*<div[^>]*>\s*<a[^>]*>([^<]{5,300})</a>', b, re.S)
        if not mz:
            mz = re.search(r'registry-entry__body-href[^>]*>\s*([^<]{5,300})</a>', b, re.S)
        if mz:
            zak = re.sub(r'\s+', ' ', mz.group(1)).strip()
        pred = ''
        mp = re.search(r'registry-entry__body-value[^>]*>\s*([^<]{5,400})<', b, re.S)
        if mp:
            pred = re.sub(r'\s+', ' ', mp.group(1)).strip()
        out.append({'nomer': nomer, 'zakazchik': zak, 'predmet': pred})
    # дедуп по номеру внутри страницы
    vid, res = set(), []
    for o in out:
        if o['nomer'] in vid:
            continue
        vid.add(o['nomer'])
        res.append(o)
    return res


sobrano, syryo, oshibki = {}, '', collections.Counter()
po_slovu = collections.Counter()
for slovo in SLOVA:
    for st in range(1, STRANIC + 1):
        try:
            u, html = tyanut(slovo, st)
        except Exception as e:  # noqa: BLE001
            oshibki['%s: %s' % (slovo, str(e)[:40])] += 1
            break
        ks = kartochki(html)
        if not ks and not syryo:
            i = html.find('regNumber=')
            syryo = html[max(0, i - 1500):i + 1500] if i > 0 else html[:2500]
        if not ks:
            break
        for o in ks:
            o['slovo'] = slovo
            o['ssylka'] = ('https://zakupki.gov.ru/epz/order/notice/notice-info/'
                           'common-info.html?noticeInfoId=&regNumber=' + o['nomer'])
            o['ssylka_poiska'] = u
            if o['nomer'] in sobrano:
                sobrano[o['nomer']]['slova'].add(slovo)
            else:
                o['slova'] = {slovo}
                sobrano[o['nomer']] = o
        po_slovu[slovo] += len(ks)
        time.sleep(0.6)

# сшивка имени заказчика с боевой базой -> ИНН (помечаем, что он СШИТ, а не из документа)
imena = {}
if os.path.exists(BAZA):
    try:
        cx = sqlite3.connect('file:%s?mode=ro' % BAZA.replace('\\', '/'), uri=True)
        for inn, nm in cx.execute('select inn, name from companies where name is not null'):
            k = re.sub(r'[^А-ЯA-Z0-9]', '', (nm or '').upper())
            if len(k) > 5:
                imena.setdefault(k, str(inn))
        cx.close()
    except Exception as e:  # noqa: BLE001
        oshibki['база имён: %s' % str(e)[:40]] += 1

potok = []
for o in sobrano.values():
    k = re.sub(r'[^А-ЯA-Z0-9]', '', o['zakazchik'].upper())
    inn = imena.get(k, '')
    potok.append({
        'nomer': o['nomer'],
        'zakazchik': o['zakazchik'],
        'inn': inn,
        'inn_otkuda': 'сшит по названию с enrich.db' if inn else 'не найден',
        'predmet': o['predmet'][:300],
        'slova': ' | '.join(sorted(o['slova'])),
        'istochniki': o['ssylka'] + ' | ' + o['ssylka_poiska'],
        'istochnikov': 2,
        'podozrenie': 'посредник по названию' if POSREDNIK.search(o['zakazchik']) else '',
        'kto': '3-я сессия, ЕИС по словам',
    })
with io.open(VYHOD, 'w', encoding='utf-8') as f:
    for o in potok:
        f.write(json.dumps(o, ensure_ascii=False) + '\n')

vylozheno = 'не выкладывала'
try:
    o2 = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request('%s/%s' % (os.environ.get('DROP_URL', '').rstrip('/'),
                                            os.path.basename(VYHOD)),
                                 data=io.open(VYHOD, 'rb').read(), method='PUT',
                                 headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
    vylozheno = o2.open(req, timeout=300).read().decode('utf-8', 'replace')[:110]
except Exception as e:  # noqa: BLE001
    vylozheno = 'не выложено: %s' % str(e)[:90]

s_inn = [o for o in potok if o['inn']]
if syryo:
    print('\n########## РАЗБОР ДАЛ НОЛЬ — вот сырая разметка вокруг regNumber')
    print(re.sub(r'\s+', ' ', syryo)[:1800])
print('\n\n########## ПРИМЕРЫ')
for o in potok[:5]:
    print('  %-12s %-46s инн %-12s %s' % (o['nomer'], o['zakazchik'][:46], o['inn'] or '—',
                                          o['slova'][:30]))
    print('     %s' % o['predmet'][:130])
print('\n########## ЧИСЛА')
print('  извещений собрано      %6d' % len(potok))
print('  разных заказчиков      %6d' % len({o['zakazchik'] for o in potok if o['zakazchik']}))
print('  ИНН сшит по названию   %6d  (разных ИНН %d)'
      % (len(s_inn), len({o['inn'] for o in s_inn})))
print('  помечено «посредник»   %6d' % sum(1 for o in potok if o['podozrenie']))
print('  --- по слову')
for k, v in po_slovu.most_common():
    print('     %-36s %6d' % (k, v))
if oshibki:
    print('  --- ошибки')
    for k, v in oshibki.most_common(8):
        print('     %-56s %4d' % (k[:56], v))
print('  файл: %s' % VYHOD)
print('  выложено: %s' % vylozheno)
print('ИТОГ ' + json.dumps({'извещений': len(potok), 'заказчиков': len({o['zakazchik'] for o in potok if o['zakazchik']}),
                            'с ИНН': len(s_inn)}, ensure_ascii=False))
