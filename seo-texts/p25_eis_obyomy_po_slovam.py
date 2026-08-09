# -*- coding: utf-8 -*-
"""ЕИС: объёмы по НЕ-центробежным словам. Счётчик читаю тем, что на странице ЕСТЬ.

Два диагноза предыдущего захода, оба про мой прибор:

1. Счётчик. Я искала «Найдено», а ЕИС пишет «Результаты поиска более N записей». Отсюда
   «найдено ?» у всех тринадцати кодов — не ЕИС молчал, а я спрашивала не тем словом.
2. Фильтр ОКПД2 НЕ ПРИМЕНЯЕТСЯ. Доказательство прямое:

       okpd2IdsCodes=28.13.2   -> «более 41 000 000 записей»
       без фильтров вообще     -> «более 41 000 000 записей»   <- то же самое
       searchString=компрессор -> «более 70 000 записей»       <- а текст РАБОТАЕТ

   Значит `okpd2IdsCodes` ЕИС игнорирует (ему нужны внутренние идентификаторы, не коды),
   а текстовый поиск живой. Код как ключ откладываю до правильного параметра и беру то,
   что работает сегодня.

Спрашиваю восемь слов, которых нам не хватает по замеру покрытия, плюс «компрессор» как
опорную точку — если у всех выйдет 41 млн, значит фильтр снова не применился, и это будет
видно сразу.
"""
import json
import re
import ssl
import time
import urllib.parse
import urllib.request

SLOVA = ['компрессор', 'винтовой компрессор', 'поршневой компрессор', 'генератор азота',
         'генератор кислорода', 'азотная станция', 'кислородная станция',
         'передвижная компрессорная станция', 'осушитель сжатого воздуха',
         'воздухоразделительная установка', 'воздуходувка', 'компрессорная станция']
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0.0.0 Safari/537.36')
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
op = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                 urllib.request.ProxyHandler({}))
SCHET = re.compile(r'Результаты поиска\s*(?:более\s*)?([\d\s ]{1,15})\s*записей', re.I)

itog = {}
for slovo in SLOVA:
    url = ('https://zakupki.gov.ru/epz/order/extendedsearch/results.html'
           '?fz44=on&fz223=on&searchString=%s&publishDateFrom=01.01.2025'
           % urllib.parse.quote(slovo))
    try:
        h = op.open(urllib.request.Request(url, headers={'User-Agent': UA}),
                    timeout=90).read().decode('utf-8', 'replace')
    except Exception as e:  # noqa: BLE001
        itog[slovo] = 'ОШИБКА: %s' % str(e)[:70]
        print('  %-36s %s' % (slovo, itog[slovo]))
        time.sleep(2)
        continue
    tx = re.sub(r'<[^>]+>', ' ', re.sub(r'<script.*?</script>', ' ', h, flags=re.S | re.I))
    tx = re.sub(r'\s+', ' ', tx)
    m = SCHET.search(tx)
    n = re.sub(r'\D', '', m.group(1)) if m else ''
    itog[slovo] = int(n) if n else '?'
    print('  %-36s %s' % (slovo, '{:,}'.format(int(n)).replace(',', ' ') if n else '?'))
    time.sleep(2)

chisla = [v for v in itog.values() if isinstance(v, int)]
print('\n\n########## ЧИСЛА')
print('  слов опрошено        %d' % len(SLOVA))
print('  ответили числом      %d' % len(chisla))
print('  разных значений      %d' % len(set(chisla)))
if len(set(chisla)) <= 1 and len(chisla) > 3:
    print('  ВНИМАНИЕ: у всех слов одно число — фильтр НЕ применён, числам не верить')
elif chisla:
    print('  ЗАСЛОН ПРОЙДЕН: значения разные, значит поиск фильтрует')
print('ИТОГ ' + json.dumps(itog, ensure_ascii=False))
