# -*- coding: utf-8 -*-
"""Расхождение счётчиков: у 1-й сессии «поршневой компрессор 7 700», у меня 2 400. Кто прав.

Числа разошлись втрое, и это не спор о вкусе — это разный ЗАПРОС. В моём сборщике зашито
`publishDateFrom=01.01.2025`, у соседа окна нет. Если дело в нём, то мой парк собран только
по публикациям за последние полтора года, а машина, купленная в 2019-м, у предприятия
СТОИТ до сих пор — и я её не вижу.

Меряю один и тот же счётчик ЕИС четырьмя окнами. Заодно снимаю форму «более N записей»,
о которую сосед споткнулся: у крупных выдач ЕИС пишет не число, а «более 70 000».

Числа в КОНЦЕ.
"""
import json
import re
import ssl
import time
import urllib.parse
import urllib.request

SLOVA = ['поршневой компрессор', 'винтовой компрессор', 'генератор кислорода',
         'генератор азота', 'воздуходувка']
OKNA = [('без окна', ''), ('с 01.01.2025', '&publishDateFrom=01.01.2025'),
        ('с 01.01.2020', '&publishDateFrom=01.01.2020'),
        ('с 01.01.2015', '&publishDateFrom=01.01.2015')]
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0.0.0 Safari/537.36')
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
net = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                  urllib.request.ProxyHandler({}))
TEG = re.compile(r'<[^>]+>')
# три формы счётчика: «найдено N заказов», «более N записей», «N записей»
FORMY = [re.compile(r'найдено\s*([\d\s ]+)\s*зак', re.I),
         re.compile(r'более\s*([\d\s ]+)\s*запис', re.I),
         re.compile(r'([\d\s ]{3,})\s*запис', re.I)]
tab = {}
for slovo in SLOVA:
    tab[slovo] = {}
    for imya, hvost in OKNA:
        u = ('https://zakupki.gov.ru/epz/order/extendedsearch/results.html'
             '?fz44=on&fz223=on&searchString=%s%s&pageNumber=1'
             % (urllib.parse.quote(slovo), hvost))
        try:
            h = net.open(urllib.request.Request(u, headers={'User-Agent': UA,
                                                            'Accept-Language': 'ru'}),
                         timeout=90).read().decode('utf-8', 'replace')
            t = re.sub(r'\s+', ' ', TEG.sub(' ', h))
            znach = None
            for f in FORMY:
                m = f.search(t)
                if m:
                    znach = int(re.sub(r'\D', '', m.group(1)) or 0)
                    break
            tab[slovo][imya] = znach
        except Exception as e:  # noqa: BLE001
            tab[slovo][imya] = 'ошибка %s' % str(e)[:24]
        time.sleep(1.2)

print('\n\n########## СЧЁТЧИК ЕИС ПО ОКНАМ ПУБЛИКАЦИИ')
print('  %-26s %12s %12s %12s %12s' % ('слово', *[o[0] for o in OKNA]))
for slovo in SLOVA:
    print('  %-26s %12s %12s %12s %12s'
          % (slovo, *[tab[slovo].get(o[0]) for o in OKNA]))
print('\n########## ЧИСЛА')
bez = [tab[s].get('без окна') for s in SLOVA if isinstance(tab[s].get('без окна'), int)]
s25 = [tab[s].get('с 01.01.2025') for s in SLOVA if isinstance(tab[s].get('с 01.01.2025'), int)]
if bez and s25:
    print('  сумма без окна        %7d' % sum(bez))
    print('  сумма с 01.01.2025    %7d  (%.0f%% от всего)'
          % (sum(s25), 100.0 * sum(s25) / max(1, sum(bez))))
print('ИТОГ ' + json.dumps({'без окна': sum(bez) if bez else None,
                            'с 2025': sum(s25) if s25 else None}, ensure_ascii=False))
