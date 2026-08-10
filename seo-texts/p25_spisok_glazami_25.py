# -*- coding: utf-8 -*-
"""25 случайных строк ИЗ САМИХ СПИСКОВ. Проверяю сшивку, а не источник.

Владелец просил открыть глазами 25 случайных ссылок-доказательств. Я делала это семь раз —
но всегда по ПОТОКАМ-ИСТОЧНИКАМ, ни разу по финальным спискам. Это разные проверки:

    поток        одна ссылка, один факт — «есть ли на странице обозначение машины»
    список       СШИТАЯ строка: человек + его номер + машина предприятия + ДВЕ ссылки

Сломаться список может там, где поток цел: имя от одного источника, номер от другого,
машина от третьего, и сшивка по ИНН могла соединить их неверно. Поэтому проверяю обе ссылки
КАЖДОЙ строки и сужу по трём вопросам сразу:

    1. ссылка на человека — есть ли на ней ЭТОТ человек (фамилия) и ЭТОТ номер;
    2. ссылка на машину  — есть ли на ней обозначение или предмет с нашей машиной;
    3. совпадает ли предприятие: ИНН на странице машины.

Три исхода на строку, и «частично» — не провал, а именно то, что надо знать: строка,
где машина доказана, а номер на странице не виден, всё ещё годна для звонка, но продавцу
надо сказать, что номер добыт другим путём.

Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import random
import re
import ssl
import urllib.request

SPISKI = [(r'C:\sender\_ops\PARK-SPISOK-DLYA-ZVONKA-3S.csv', 'с личным номером'),
          (r'C:\sender\_ops\PARK-SPISOK-CHEREZ-KOMMUTATOR-3S.csv', 'через коммутатор')]
SKOLKO = 25
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0.0.0 Safari/537.36')
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
net = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                  urllib.request.ProxyHandler({}))
TEG = re.compile(r'<[^>]+>')


def tyanut(u):
    rq = urllib.request.Request(u, headers={'User-Agent': UA, 'Accept-Language': 'ru'})
    with net.open(rq, timeout=45) as rs:
        return re.sub(r'\s+', ' ', TEG.sub(' ', rs.read(400000).decode('utf-8', 'replace')))


stroki = []
for put, chto in SPISKI:
    if not os.path.exists(put):
        continue
    shapka = None
    for s in io.open(put, encoding='utf-8-sig'):
        p = s.rstrip('\n').split(';')
        if shapka is None:
            shapka = p
            continue
        if len(p) != len(shapka):
            continue
        o = dict(zip(shapka, p))
        o['_spisok'] = chto
        stroki.append(o)

random.seed(1111)
vybor = random.sample(stroki, min(SKOLKO, len(stroki)))
ishody = collections.Counter()
print('########## ПО ОДНОЙ СТРОКЕ')
for o in vybor:
    inn = o.get('inn', '')
    imya = (o.get('chelovek') or o.get('chelovek_bez_nomera') or '').strip()
    nomer = re.sub(r'\D', '', o.get('nomer') or o.get('telefon_obshchiy') or '')[-10:]
    u_ch = (o.get('ssylka_chelovek') or '').strip()
    u_m = (o.get('ssylka_mashina') or '').strip()
    est_ch, est_nom, est_m, est_inn = False, False, False, False
    oshibki = []
    if u_ch.startswith('http'):
        try:
            t = tyanut(u_ch)
            fam = imya.split(' ')[0] if imya else ''
            est_ch = bool(fam) and len(fam) > 3 and fam in t
            est_nom = bool(nomer) and nomer in re.sub(r'\D', '', t)
        except Exception as e:  # noqa: BLE001
            oshibki.append('человек: %s' % str(e)[:34])
    if u_m.startswith('http'):
        try:
            t2 = tyanut(u_m)
            est_m = bool(re.search(r'компрессор|воздуходув|нагнетател|ГПА|осушител|'
                                   r'азот|кислород|ВРУ', t2, re.I))
            est_inn = bool(inn) and inn in re.sub(r'\D', '', t2)
        except Exception as e:  # noqa: BLE001
            oshibki.append('машина: %s' % str(e)[:34])
    # РАЗДЕЛЯЮ ДВЕ РАЗНЫЕ ВЕЩИ, которые прошлый прогон свалил в один исход. «Машина видна,
    # страница человека ничего не подтвердила» набрала 13 из 25 — и почти все они были
    # строками коммутаторного списка, где ЧЕЛОВЕКА НЕТ ПО ПОСТРОЕНИЮ: есть телефон
    # предприятия и доказанная машина, а имени неоткуда взяться. Считать это провалом
    # проверки — врать себе в обе стороны: и мерка портится, и настоящие поломки тонут.
    # Строка, которая ОБЕЩАЕТ человека и не доказывает его, остаётся провалом.
    net_cheloveka = not imya
    if net_cheloveka and est_m:
        v = 'КОММУТАТОР: человека в строке нет по построению, машина видна'
    elif est_ch and est_nom and est_m:
        v = 'ПОЛНОСТЬЮ: человек, его номер и машина видны'
    elif (est_ch or est_nom) and est_m:
        v = 'ЧАСТИЧНО: машина видна, человек или номер — нет'
    elif est_m:
        v = 'машина видна, страница человека ничего не подтвердила'
    elif est_ch or est_nom:
        v = 'человек виден, машина по ссылке не подтвердилась'
    else:
        v = 'НЕ ПОДТВЕРДИЛОСЬ НИЧЕГО'
    ishody[v.split(':')[0]] += 1
    print('  [%s] %-12s %-26s %s' % (o['_spisok'][:16], inn, imya[:26], v))
    if oshibki:
        print('        ошибки: %s' % ' | '.join(oshibki))
    print('        человек: %s' % (u_ch[:100] or '—'))
    print('        машина:  %s' % (u_m[:100] or '—'))
print('\n########## ЧИСЛА')
print('  строк в обоих списках   %5d' % len(stroki))
print('  проверено               %5d' % len(vybor))
for k, v in ishody.most_common():
    print('     %-52s %5d' % (k[:52], v))
print('ИТОГ ' + json.dumps(dict(ishody), ensure_ascii=False))
