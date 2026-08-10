# -*- coding: utf-8 -*-
"""ЕИС по ОБОЗНАЧЕНИЮ: ищу форму запроса, при которой обозначение реально фильтрует выдачу.

Заход по 45 сериям дал 330 извещений и **ноль** подтверждений: слова запроса нет ни в одной
собранной карточке, а «новые ИНН» оказались больницами, администрациями и Росреестром. Это
не находка, это генеральная лента: полнотекстовый поиск ЕИС проглотил «К-250-61-5» и вернул
всё подряд. Собственный заслон «слово подтверждено текстом» поймал это сразу — потому 172
ИНН в парк НЕ пошли.

Теперь ищу, есть ли форма, при которой фильтр применяется. Проверяю шесть написаний одного
и того же обозначения и меряю ОДНИМ числом: сколько раз обозначение встречается в тексте
выдачи. Ноль — форма не работает, как бы красиво ни выглядел ответ.

    К-250-61-5      как в документах
    "К-250-61-5"    в кавычках — точная фраза
    К250615         без разделителей
    К 250 61 5      через пробелы
    К-250           короткий корень серии
    компрессор К-250-61-5   слово плюс обозначение

Отрицательный контроль: седьмым идёт заведомо несуществующее обозначение «Щ-999-88-7».
Если и по нему придут извещения — значит выдача не фильтруется вовсе, и все остальные
числа этого замера ничего не значат.

Числа в КОНЦЕ.
"""
import collections
import json
import re
import ssl
import time
import urllib.parse
import urllib.request

OBOZN = 'К-250-61-5'
FORMY = [('как в документах', OBOZN),
         ('в кавычках', '"%s"' % OBOZN),
         ('без разделителей', 'К250615'),
         ('через пробелы', 'К 250 61 5'),
         ('короткий корень', 'К-250'),
         ('слово плюс обозначение', 'компрессор %s' % OBOZN),
         ('ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ', 'Щ-999-88-7')]
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0.0.0 Safari/537.36')
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
net = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                  urllib.request.ProxyHandler({}))
TEG = re.compile(r'<[^>]+>')
SCHET = re.compile(r'найдено\s*([\d\s ]+)\s*зак', re.I)
KARTOCHKA = re.compile(r'registry-entry__header-mid__number')

itogi = []
for imya, zapros in FORMY:
    u = ('https://zakupki.gov.ru/epz/order/extendedsearch/results.html'
         '?fz44=on&fz223=on&searchString=%s&publishDateFrom=01.01.2020&pageNumber=1'
         % urllib.parse.quote(zapros))
    try:
        h = net.open(urllib.request.Request(u, headers={'User-Agent': UA,
                                                        'Accept-Language': 'ru'}),
                     timeout=60).read().decode('utf-8', 'replace')
    except Exception as e:  # noqa: BLE001
        itogi.append((imya, zapros, '—', 0, 0, 0, str(e)[:40]))
        continue
    t = re.sub(r'\s+', ' ', TEG.sub(' ', h))
    m = SCHET.search(t)
    schet = re.sub(r'\D', '', m.group(1)) if m else ''
    kartochek = len(KARTOCHKA.findall(h))
    # сколько раз обозначение (в любом написании) встречается в тексте выдачи
    goloe = re.sub(r'\W', '', OBOZN).lower()
    vstrech = len(re.findall(re.escape(goloe), re.sub(r'\W', '', t).lower()))
    itogi.append((imya, zapros, schet or '?', kartochek, vstrech, len(t), ''))
    time.sleep(1.0)

print('\n\n########## ЧТО ОТВЕТИЛА КАЖДАЯ ФОРМА ЗАПРОСА')
for imya, zapros, schet, kart, vstrech, dlina, err in itogi:
    print('  %-24s «%-22s» счётчик ЕИС %-8s карточек %2d, обозначение в тексте %3d раз%s'
          % (imya, zapros[:22], schet, kart, vstrech, ('  ' + err) if err else ''))
rabochie = [x for x in itogi if x[0] != 'ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ' and x[4] > 0 and x[3] > 0]
kontrol = [x for x in itogi if x[0] == 'ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ']
print('\n########## ЧИСЛА')
print('  форм проверено                 %2d' % len(itogi))
print('  форм, где обозначение РЕАЛЬНО в выдаче %2d' % len(rabochie))
for x in rabochie:
    print('     РАБОЧАЯ: %-24s карточек %d, обозначение %d раз' % (x[0], x[3], x[4]))
if kontrol:
    k = kontrol[0]
    print('  отрицательный контроль «Щ-999-88-7»: карточек %d, счётчик %s' % (k[3], k[2]))
    print('     %s' % ('выдача НЕ фильтруется — всем числам выше грош цена'
                       if k[3] > 0 else 'по несуществующему обозначению пусто — фильтр работает'))
print('ИТОГ ' + json.dumps({'форм': len(itogi), 'рабочих': len(rabochie),
                            'контроль карточек': kontrol[0][3] if kontrol else None},
                           ensure_ascii=False))
