# -*- coding: utf-8 -*-
"""РТС-тендер и Росэлторг: перепроверка. Ноль был диагнозом прибора, а не пустотой площадки.

Что было записано раньше и почему это НЕ ответ:

    РТС         503 — «сервис недоступен». Одинаковый ответ на все запросы это диагноз
                ПРИБОРА: либо площадка не пускает серверный адрес, либо я стучусь не туда.
    Росэлторг   404 на моём адресе, и я сама записала «мой URL неверен». Неверный адрес
                опровергает адрес, а не площадку.

Поэтому здесь не повтор того же запроса, а РАЗБОР: у каждой площадки спрашиваю несколько
разных входов и печатаю, ЧТО ИМЕННО ответил сервер на каждый. Правило дня: ноль, повторённый
одинаково, — это один диагноз прибора; чтобы он стал фактом о площадке, нужен вход, который
у неё точно есть.

Заслон на самообман: если страница пришла, проверяю, есть ли в ней СЛОВО ЗАПРОСА. Ответ 200
с общей лентой — это не «нашли по компрессору», это площадка проигнорировала фильтр.

Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import re
import ssl
import urllib.parse
import urllib.request

SLOVO = 'компрессор'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0.0.0 Safari/537.36')
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
net = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                  urllib.request.ProxyHandler({}))
TEG = re.compile(r'<(script|style)[^>]*>.*?</\1>|<[^>]+>', re.S | re.I)
KV = urllib.parse.quote(SLOVO)
VHODY = [
    ('РТС, корень', 'https://www.rts-tender.ru/', None),
    ('РТС, поиск закупок', 'https://www.rts-tender.ru/poisk/search?keywords=%s' % KV, None),
    ('РТС, 223-ФЗ', 'https://223.rts-tender.ru/supplier/auction/Trade/Search.aspx?searchText=%s'
     % KV, None),
    ('РТС, api поиска', 'https://api.rts-tender.ru/api/search/v1/procedures?text=%s' % KV, None),
    ('Росэлторг, корень', 'https://www.roseltorg.ru/', None),
    ('Росэлторг, поиск', 'https://www.roseltorg.ru/procedures?search=%s' % KV, None),
    ('Росэлторг, старый путь', 'https://www.roseltorg.ru/procedures/search?query=%s' % KV, None),
    ('Росэлторг, api', 'https://www.roseltorg.ru/api/procedures?query=%s' % KV, None),
    ('ЕИС для сравнения', 'https://zakupki.gov.ru/epz/order/extendedsearch/results.html'
     '?fz44=on&fz223=on&searchString=%s&publishDateFrom=01.01.2025&pageNumber=1' % KV, None),
]

ishody, podrobno = collections.Counter(), []
for imya, u, dannye in VHODY:
    kod, dlina, est_slovo, err = '', 0, False, ''
    try:
        rq = urllib.request.Request(u, headers={'User-Agent': UA, 'Accept-Language': 'ru',
                                                'Accept': 'text/html,application/json,*/*'})
        with net.open(rq, timeout=45) as rs:
            telo = rs.read(500000).decode('utf-8', 'replace')
            kod = str(rs.status)
    except urllib.error.HTTPError as e:  # noqa: PERF203
        kod, telo = str(e.code), (e.read(200000).decode('utf-8', 'replace') if e.fp else '')
        err = 'HTTPError'
    except Exception as e:  # noqa: BLE001
        kod, telo, err = '—', '', str(e)[:60]
    dlina = len(telo)
    t = re.sub(r'\s+', ' ', TEG.sub(' ', telo))
    est_slovo = SLOVO[:8].lower() in t.lower()
    # ЗАСЛОН: сколько раз слово встречается — один раз это может быть пункт меню
    skolko = len(re.findall(SLOVO[:8], t, re.I))
    ishody['%s -> %s' % (imya, kod)] += 1
    podrobno.append((imya, kod, dlina, skolko, err, u[:88]))

print('\n\n########## ЧТО ОТВЕТИЛА КАЖДАЯ ТОЧКА ВХОДА')
for imya, kod, dlina, skolko, err, u in podrobno:
    print('  %-26s код %-5s тело %7d знаков, «%s» встречается %3d раз%s'
          % (imya, kod, dlina, SLOVO[:8], skolko, ('   ' + err) if err else ''))
    print('        %s' % u)
zhivye = [p for p in podrobno if p[1] == '200' and p[3] > 1]
print('\n########## ЧИСЛА')
print('  точек входа проверено      %3d' % len(podrobno))
print('  ответили 200 И со словом   %3d' % len(zhivye))
for p in zhivye:
    print('     ЖИВАЯ: %-26s слово %d раз' % (p[0], p[3]))
print('  --- коды ответов')
for k, v in ishody.most_common():
    print('     %-56s %3d' % (k[:56], v))
print('ИТОГ ' + json.dumps({'входов': len(podrobno), 'живых': len(zhivye),
                            'живые': [p[0] for p in zhivye]}, ensure_ascii=False))
