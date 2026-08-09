# -*- coding: utf-8 -*-
"""Что реально лежит в карточке выдачи ЕИС. Заказчик у меня вышел пустым у всех 544.

Числа второго захода честные: счётчики у слов разные, у «воздухоразделительной установки»
разобрано 8 при счётчике 8 — значит фильтр применяется и разбор ленты идёт по делу. Но
колонка «заказчик» пуста у ВСЕХ строк, а значит мои шаблоны подписей не те. Смотрю живую
карточку целиком, а не гадаю по классам.
"""
import re
import ssl
import urllib.parse
import urllib.request

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0.0.0 Safari/537.36')
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
op = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                 urllib.request.ProxyHandler({}))
u = ('https://zakupki.gov.ru/epz/order/extendedsearch/results.html'
     '?fz44=on&fz223=on&searchString=%s&publishDateFrom=01.01.2025'
     % urllib.parse.quote('генератор кислорода'))
h = op.open(urllib.request.Request(u, headers={'User-Agent': UA}), timeout=90).read().decode('utf-8', 'replace')
i = h.find('search-registry-entry-block')
kus = h[i:i + 7000]
print('########## КЛАССЫ ВНУТРИ ПЕРВОЙ КАРТОЧКИ')
kl = {}
for m in re.finditer(r'class="([^"]{4,60})"', kus):
    kl[m.group(1)] = kl.get(m.group(1), 0) + 1
for k, v in sorted(kl.items(), key=lambda x: -x[1])[:22]:
    print('  %-52s %d' % (k[:52], v))
print('\n########## ПЛОСКИЙ ТЕКСТ ПЕРВОЙ КАРТОЧКИ')
t = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', kus))
print(t[:1400])
print('\nИТОГ {"смотрела": "разметку карточки ЕИС"}')
