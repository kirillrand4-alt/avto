# -*- coding: utf-8 -*-
"""Что я на самом деле вытащила из реестра организаций ЕИС. 157 «названий» — это АДРЕСА.

Заслон «ИНН обязан быть на странице» отработал: 157 из 200 организаций найдены. Но я
посмотрела на добытое глазами, и там не имена:

    0266017771  «453256, Г.. САЛАВАТ, УЛ. МОЛОДОГВАРДЕЙЦЕВ, Д.26»
    0268000188  «453120, РЕСПУБЛИКА БАШКОРТОСТАН, Г.. СТЕРЛИТАМАК, УЛ. ДНЕПРОВСКАЯ, Д.3»

Мой шаблон взял первое подходящее поле карточки, а первым там стоит адрес. Ровно та ошибка,
про которую я сама записала правило: «прежде чем чинить разбор, посмотреть образец глазами».
На этот раз посмотрела до отчёта, а не после.

Смотрю разметку карточки организации целиком и печатаю ВСЕ пары «подпись — значение».
"""
import re
import ssl
import urllib.request

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0.0.0 Safari/537.36')
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
op = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                 urllib.request.ProxyHandler({}))
TEG = re.compile(r'<[^>]+>')
u = ('https://zakupki.gov.ru/epz/organization/search/results.html?searchString=0266017771'
     '&morphology=on&sortBy=UPDATE_DATE')
h = op.open(urllib.request.Request(u, headers={'User-Agent': UA}), timeout=60).read().decode(
    'utf-8', 'replace')
i = h.find('registry-entry')
kus = h[max(0, i - 500):i + 6000]
print('########## КЛАССЫ В КАРТОЧКЕ ОРГАНИЗАЦИИ')
kl = {}
for m in re.finditer(r'class="([^"]{4,60})"', kus):
    kl[m.group(1)] = kl.get(m.group(1), 0) + 1
for k, v in sorted(kl.items(), key=lambda x: -x[1])[:18]:
    print('  %-54s %d' % (k[:54], v))
print('\n########## ПЛОСКИЙ ТЕКСТ КАРТОЧКИ')
print(re.sub(r'\s+', ' ', TEG.sub(' ', kus))[:1200])
print('\nИТОГ {"смотрела": "разметку карточки организации ЕИС"}')
