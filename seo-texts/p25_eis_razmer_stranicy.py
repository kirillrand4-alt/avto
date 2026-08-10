# -*- coding: utf-8 -*-
"""20 страниц дают 200 карточек, а не 1 000: ЕИС отдаёт по 10. Проверяю размер страницы.

Замер, из-за которого это вскрылось: срез «компрессор» за 2022 год — счётчик ЕИС 4 900,
а разобрано 200 при STRANIC=20. Значит на странице ДЕСЯТЬ карточек, и весь мой постраничный
обход в пять раз мельче, чем я думала.

У ЕИС есть параметр `recordsPerPage`. Но добавлять параметры «на глаз» я уже пробовала —
именно так первый сбор дал 1 929 строк мимо цели. Поэтому: проверяю на ОДНОМ слове, меряю
не веру, а три числа, и сравниваю с тем же запросом без параметра.

    карточек на странице   сколько блоков извещений реально разобрано
    слово в тексте         фильтр применился или отдана общая лента
    номера карточек        совпадают ли первые номера у обоих запросов (иначе выдача другая)

Числа в КОНЦЕ.
"""
import json, re, ssl, urllib.parse, urllib.request
SLOVO = 'компрессор'
BAZA = ('https://zakupki.gov.ru/epz/order/extendedsearch/results.html'
        '?fz44=on&fz223=on&searchString=%s&publishDateFrom=01.01.2022'
        '&publishDateTo=31.12.2022&pageNumber=1' % urllib.parse.quote(SLOVO))
VARIANTY = [('как сейчас', ''), ('recordsPerPage=50', '&recordsPerPage=50'),
            ('recordsPerPage=_50', '&recordsPerPage=_50'), ('pageSize=50', '&pageSize=50')]
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0.0.0 Safari/537.36')
ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
net = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                  urllib.request.ProxyHandler({}))
BLOK = re.compile(r'search-registry-entry-block')
REG = re.compile(r'regNumber=(\d{11,25})')
TEG = re.compile(r'<[^>]+>')
itogi = []
for imya, hvost in VARIANTY:
    u = BAZA + hvost
    try:
        h = net.open(urllib.request.Request(u, headers={'User-Agent': UA,
                                                        'Accept-Language': 'ru'}),
                     timeout=60).read().decode('utf-8', 'replace')
    except Exception as e:
        itogi.append((imya, 0, False, [], str(e)[:40])); continue
    t = re.sub(r'\s+', ' ', TEG.sub(' ', h))
    nomera = REG.findall(h)[:3]
    itogi.append((imya, len(BLOK.findall(h)), SLOVO[:8] in t.lower(), nomera, ''))
print('\n\n########## ЧТО ВЕРНУЛА КАЖДАЯ ФОРМА')
for imya, kart, slovo, nom, err in itogi:
    print('  %-22s карточек %3d | слово в тексте: %-3s | первые номера: %s%s'
          % (imya, kart, 'да' if slovo else 'НЕТ', ', '.join(nom[:2]), ('  ' + err) if err else ''))
baz = itogi[0]
luchshe = [x for x in itogi[1:] if x[1] > baz[1] and x[2]]
print('\n########## ЧИСЛА')
print('  как сейчас: %d карточек на странице' % baz[1])
for x in luchshe:
    print('  РАБОЧАЯ ФОРМА: %-22s %d карточек, прирост в %.1f раза'
          % (x[0], x[1], (x[1] / max(1, baz[1]))))
if not luchshe:
    print('  ни одна форма не увеличила страницу — размер задан площадкой, не мной')
print('ИТОГ ' + json.dumps({'сейчас': baz[1],
                            'лучшие': [(x[0], x[1]) for x in luchshe]}, ensure_ascii=False))
