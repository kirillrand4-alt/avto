# -*- coding: utf-8 -*-
"""ЕИС по ОКПД2, второй заход: TLS. Мой ноль был прибором, а не пустым ЕИС.

Первый заход дал SSL CERTIFICATE_VERIFY_FAILED на всех 15 кодах, и это соблазнительно было
записать как «ЕИС закрыт». У соседа это уже оплачено и записано: `eis_plan` ходит НАПРЯМУЮ
(без прокси) и с `https_errors=True`, потому что у zakupki.gov.ru российские госсертификаты,
которых нет в наборе доверенных у python.

Делаю то же: контекст без проверки цепочки ТОЛЬКО для домена zakupki.gov.ru. Это чтение
государственного открытого реестра, не передача секретов; для всех прочих доменов проверка
остаётся.

Смотрю по каждому коду: сколько извещений и отражается ли код в ответе — если ЕИС молча
проигнорировал фильтр, число будет одинаковым у всех кодов, и это будет видно.
"""
import collections
import json
import re
import ssl
import time
import urllib.parse
import urllib.request

KODY = [('28.13.1', 'Насосы воздушные/вакуумные'), ('28.13.2', 'Компрессоры прочие'),
        ('28.13.21', 'Компрессоры холодильные'), ('28.13.23', 'Турбокомпрессоры'),
        ('28.13.24', 'Компрессоры поршневые'), ('28.13.25', 'Компрессоры ротационные'),
        ('28.13.26', 'Компрессоры центробежные'), ('28.13.28', 'Компрессоры прочие'),
        ('20.11', 'Газы промышленные'), ('20.11.11', 'Водород, азот, кислород'),
        ('28.25.14', 'Фильтрование/очистка газов'),
        ('33.12.19', 'Ремонт оборудования общего назначения'),
        ('33.12.29', 'Ремонт спецоборудования')]
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0.0.0 Safari/537.36')
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
op = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                 urllib.request.ProxyHandler({}))
BAZA = ('https://zakupki.gov.ru/epz/order/extendedsearch/results.html'
        '?fz44=on&fz223=on&okpd2IdsCodes=%s&publishDateFrom=01.01.2025&recordsPerPage=_10')
CHISLO = re.compile(r'Найдено\s*<span[^>]*>\s*([\d\s ]+)', re.I)
CHISLO2 = re.compile(r'search-results__quantity[^>]*>\s*<span[^>]*>\s*([\d\s ]+)', re.I)

itog = {}
for kod, imya in KODY:
    try:
        req = urllib.request.Request(BAZA % urllib.parse.quote(kod),
                                     headers={'User-Agent': UA,
                                              'Accept-Language': 'ru-RU,ru;q=0.9'})
        h = op.open(req, timeout=90).read().decode('utf-8', 'replace')
    except Exception as e:  # noqa: BLE001
        itog[kod] = {'имя': imya, 'ошибка': str(e)[:100]}
        print('  %-10s %-38s ОШИБКА %s' % (kod, imya[:38], str(e)[:70]))
        time.sleep(2)
        continue
    m = CHISLO.search(h) or CHISLO2.search(h)
    n = re.sub(r'\D', '', m.group(1)) if m else ''
    itog[kod] = {'имя': imya, 'найдено': n or '?', 'знаков': len(h), 'код в ответе': kod in h}
    print('  %-10s %-38s найдено %-9s ответ %6d знаков  код отражён: %s'
          % (kod, imya[:38], n or '?', len(h), kod in h))
    time.sleep(2)

chisla = [int(re.sub(r'\D', '', str(v.get('найдено', '')))) for v in itog.values()
          if str(v.get('найдено', '')).replace(' ', '').isdigit()]
print('\n\n########## ЧИСЛА')
print('  кодов опрошено         %d' % len(itog))
print('  ответили числом        %d' % len(chisla))
print('  разных значений        %d  %s' % (len(set(chisla)), sorted(set(chisla))[:8]))
if len(set(chisla)) <= 1 and len(chisla) > 3:
    print('  ВНИМАНИЕ: у всех кодов одно и то же число — фильтр ОКПД2 НЕ ПРИМЕНЁН')
print('  суммарно извещений     %d' % sum(chisla))
print('ИТОГ ' + json.dumps({k: v.get('найдено', v.get('ошибка')) for k, v in itog.items()},
                           ensure_ascii=False)[:500])
