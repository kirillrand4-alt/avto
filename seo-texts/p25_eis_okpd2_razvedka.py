# -*- coding: utf-8 -*-
"""ЕИС по ОКПД2: разведка объёмов. Ключ, который берёт ВСЕ типы разом, а не одно слово.

Владелец поймал нас на том, что мы собираем центробежку и один бренд. Слова этого не чинят:
«компрессор» приносит компрессоры, «винтовой» — винтовые, и каждый раз надо угадать слово.
ОКПД2 — это КОД, он покрывает номенклатуру целиком и не зависит от того, как заказчик
назвал предмет в тексте.

Грепом по нашему коду `окпд|okpd|okpd2` — ОДНА строка на весь `seo-texts`. То есть канал не
использован вовсе.

ЧТО ДЕЛАЮ. Беру коды-кандидаты и спрашиваю ЕИС, сколько по каждому извещений за год. Это
разведка объёма, а не выгрузка: узнать, где вообще есть что брать, прежде чем тратить заходы.
Коды проверяю по ответу ЕИС, а не считаю верными по памяти — если код неверен, поиск вернёт
ноль или ошибку, и это будет видно.

Только чтение чужого сайта, без записи в наши базы.
"""
import collections
import json
import re
import time
import urllib.parse
import urllib.request

KODY = [
    ('28.13.1', 'Насосы воздушные или вакуумные'),
    ('28.13.2', 'Компрессоры воздушные или газовые прочие'),
    ('28.13.21', 'Компрессоры для холодильного оборудования'),
    ('28.13.22', 'Компрессоры, применяемые в транспортных средствах'),
    ('28.13.23', 'Турбокомпрессоры'),
    ('28.13.24', 'Компрессоры поршневые'),
    ('28.13.25', 'Компрессоры ротационные многовальные'),
    ('28.13.26', 'Компрессоры центробежные одновальные и многовальные'),
    ('28.13.28', 'Компрессоры прочие'),
    ('20.11', 'Газы промышленные'),
    ('20.11.11', 'Водород, азот, кислород'),
    ('28.25.14', 'Оборудование для фильтрования или очистки газов'),
    ('28.29.12', 'Оборудование для фильтрования жидкостей'),
    ('33.12.19', 'Услуги по ремонту прочего оборудования общего назначения'),
    ('33.12.29', 'Услуги по ремонту прочего специального оборудования'),
]
BAZA = ('https://zakupki.gov.ru/epz/order/extendedsearch/results.html'
        '?searchString=&morphology=on&pageNumber=1&sortDirection=false&recordsPerPage=_10'
        '&fz44=on&fz223=on&okpd2Ids=&okpd2IdsCodes=%s&publishDateFrom=01.01.2025')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0.0.0 Safari/537.36')
NAYDENO = re.compile(r'Найдено\s*<span[^>]*>([\d\s ]+)</span>|найдено[^<]{0,20}?([\d\s ]{2,12})',
                     re.I)

op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
itog = {}
for kod, imya in KODY:
    url = BAZA % urllib.parse.quote(kod)
    try:
        req = urllib.request.Request(url, headers={'User-Agent': UA,
                                                   'Accept-Language': 'ru-RU,ru;q=0.9'})
        h = op.open(req, timeout=60).read().decode('utf-8', 'replace')
    except Exception as e:  # noqa: BLE001
        itog[kod] = {'имя': imya, 'ошибка': str(e)[:90]}
        print('  %-10s %-52s ОШИБКА %s' % (kod, imya[:52], str(e)[:60]))
        time.sleep(2)
        continue
    m = NAYDENO.search(h)
    chislo = ''
    if m:
        chislo = re.sub(r'\D', '', (m.group(1) or m.group(2) or ''))
    est_kod = kod in h
    itog[kod] = {'имя': imya, 'найдено': chislo or '?', 'знаков в ответе': len(h),
                 'код отражён в ответе': est_kod}
    print('  %-10s %-46s найдено %-10s страница %6d знаков  код в ответе: %s'
          % (kod, imya[:46], chislo or '?', len(h), est_kod))
    time.sleep(2)

print('\n\n########## ЧИСЛА')
vsego = 0
for k, v in itog.items():
    n = re.sub(r'\D', '', str(v.get('найдено') or ''))
    if n:
        vsego += int(n)
print('  кодов опрошено      %d' % len(itog))
print('  ответили числом     %d' % sum(1 for v in itog.values() if str(v.get('найдено', '?')).isdigit()))
print('  суммарно извещений  %d (с 01.01.2025, 44-ФЗ + 223-ФЗ)' % vsego)
print('ИТОГ ' + json.dumps(itog, ensure_ascii=False)[:900])
