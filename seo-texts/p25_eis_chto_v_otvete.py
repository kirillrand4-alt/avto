# -*- coding: utf-8 -*-
"""ЕИС ответил 200, но у ВСЕХ кодов ответ одного размера. Смотрю, что там на самом деле.

TLS починен: было SSL CERTIFICATE_VERIFY_FAILED, стало 200 и 354 350 знаков. Но:

    все 13 кодов -> ответ 354 350-354 352 знака, счётчик не разобран («найдено ?»)

Одинаковый размер у разных фильтров — это подпись «фильтр не применён», тот же признак,
что поймал сосед на четырёх вакансиях hh с разбросом в 172 знака. Значит либо параметр
называется иначе (`okpd2Ids` в ЕИС ждёт ВНУТРЕННИЕ идентификаторы, а не коды), либо
страница рисуется скриптом и числа в HTML нет вовсе.

Не гадаю: печатаю кусок ответа вокруг слов «найдено», «результат», «okpd» и первые
1 500 знаков текста. Пусть страница скажет сама.
"""
import re
import ssl
import urllib.parse
import urllib.request

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
op = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                 urllib.request.ProxyHandler({}))
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0.0.0 Safari/537.36')

VARIANTY = [
    ('okpd2IdsCodes=28.13.2', 'https://zakupki.gov.ru/epz/order/extendedsearch/results.html'
                              '?fz44=on&fz223=on&okpd2IdsCodes=28.13.2'),
    ('searchString=компрессор', 'https://zakupki.gov.ru/epz/order/extendedsearch/results.html'
                                '?fz44=on&fz223=on&searchString=' + urllib.parse.quote('компрессор')),
    ('без фильтров', 'https://zakupki.gov.ru/epz/order/extendedsearch/results.html?fz44=on&fz223=on'),
]

for imya, url in VARIANTY:
    try:
        h = op.open(urllib.request.Request(url, headers={'User-Agent': UA}),
                    timeout=90).read().decode('utf-8', 'replace')
    except Exception as e:  # noqa: BLE001
        print('\n=== %s -> ОШИБКА %s' % (imya, str(e)[:100]))
        continue
    tx = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', h, flags=re.S | re.I)
    tx = re.sub(r'<[^>]+>', ' ', tx)
    tx = re.sub(r'\s+', ' ', tx)
    print('\n\n=== %s   HTML %d знаков, текст %d' % (imya, len(h), len(tx)))
    for slovo in ('найдено', 'Найдено', 'результат', 'записей'):
        for m in list(re.finditer(slovo, tx))[:2]:
            print('   вокруг «%s»: …%s…' % (slovo, tx[max(0, m.start() - 70):m.start() + 90]))
    print('   первые 700 знаков текста: %s' % tx[:700])

print('\nИТОГ {"смотрела": "что реально в ответе ЕИС"}')
