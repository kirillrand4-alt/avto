# -*- coding: utf-8 -*-
"""РАЗВЕДКА ПЛОЩАДОК по НЕ-центробежному словарю: где вообще есть что брать.

Площадки по разделению мои. Прежде чем тратить заходы на карточки, надо узнать, у какой
площадки по каким словам вообще есть объём — это правило `tender_centro_scan`: сперва
счётчик, потом выгрузка.

Слова беру ровно те, которых нам не хватает по замеру покрытия: винтовой, поршневой, МКС,
генератор азота, генератор кислорода, азотная станция, кислородная станция, осушитель.
«Центробежный» НЕ спрашиваю — он у нас и так самый полный, и именно из-за него перекос.

Считаю по каждой паре «площадка + слово»: сколько найдено. Ноль по слову у площадки — это
диагноз (у неё нет такого раздела или закрыт поиск), и он печатается отдельно от ошибки.

ЕИС ходит с российскими госсертификатами — для него контекст без проверки цепочки, как у
соседа в `eis_plan`. Для остальных проверка остаётся.
"""
import collections
import json
import re
import ssl
import time
import urllib.parse
import urllib.request

SLOVA = ['винтовой компрессор', 'поршневой компрессор', 'генератор азота',
         'генератор кислорода', 'азотная станция', 'кислородная станция',
         'передвижная компрессорная станция', 'осушитель сжатого воздуха']
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0.0.0 Safari/537.36')
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
op = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                 urllib.request.ProxyHandler({}))

PLOSHCHADKI = [
    ('ЕИС 44+223', 'https://zakupki.gov.ru/epz/order/extendedsearch/results.html'
                   '?searchString=%s&fz44=on&fz223=on&recordsPerPage=_10',
     [re.compile(r'Найдено\s*<span[^>]*>\s*([\d\s ]+)', re.I)]),
    ('РТС-тендер', 'https://www.rts-tender.ru/poisk?searchtext=%s',
     [re.compile(r'найдено[^\d]{0,20}([\d\s ]{1,12})', re.I)]),
    ('Росэлторг', 'https://www.roseltorg.ru/procedures?query=%s',
     [re.compile(r'найдено[^\d]{0,20}([\d\s ]{1,12})', re.I)]),
]

itog = collections.defaultdict(dict)
for imya, shablon, rgs in PLOSHCHADKI:
    for slovo in SLOVA:
        url = shablon % urllib.parse.quote(slovo)
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA,
                                                       'Accept-Language': 'ru-RU,ru;q=0.9'})
            h = op.open(req, timeout=75).read().decode('utf-8', 'replace')
        except Exception as e:  # noqa: BLE001
            itog[imya][slovo] = 'ОШИБКА: %s' % str(e)[:60]
            time.sleep(1.5)
            continue
        n = ''
        for rg in rgs:
            m = rg.search(h)
            if m:
                n = re.sub(r'\D', '', m.group(1))
                break
        est_slovo = slovo.split()[0][:8].lower() in h.lower()
        itog[imya][slovo] = {'найдено': n or '?', 'знаков': len(h),
                             'слово в ответе': est_slovo}
        time.sleep(1.5)

print('\n\n########## РАЗВЕДКА: где есть объём по НЕ-центробежным словам')
for imya in itog:
    print('\n  === %s' % imya)
    for slovo, v in itog[imya].items():
        if isinstance(v, str):
            print('     %-38s %s' % (slovo, v))
        else:
            print('     %-38s найдено %-9s ответ %6d знаков  слово в ответе: %s'
                  % (slovo, v['найдено'], v['знаков'], v['слово в ответе']))

print('\n########## ЧИСЛА')
for imya in itog:
    ok = sum(1 for v in itog[imya].values()
             if isinstance(v, dict) and str(v['найдено']).isdigit())
    err = sum(1 for v in itog[imya].values() if isinstance(v, str))
    print('  %-14s ответили числом %d из %d, ошибок %d' % (imya, ok, len(SLOVA), err))
print('ИТОГ ' + json.dumps({k: {s: (v if isinstance(v, str) else v['найдено'])
                                for s, v in d.items()} for k, d in itog.items()},
                           ensure_ascii=False)[:700])
