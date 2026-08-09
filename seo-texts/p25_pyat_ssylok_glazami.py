# -*- coding: utf-8 -*-
"""Пять случайных ссылок-доказательств: открыть и сказать, ведут ли они НА ДОКАЗАТЕЛЬСТВО.

Правило владельца: каждый факт доказывается ссылкой, которая ведёт на доказательство. Пока
ссылку не открыли — это строка в таблице, а не доказательство. Беру пять случайных из
словаря серий и смотрю, что по ним отдаётся.

Три исхода, и они разные:
    ДОКАЗЫВАЕТ    страница открылась и на ней есть ОБОЗНАЧЕНИЕ серии
    ОТКРЫЛАСЬ, НО обозначения на ней нет — ссылка ведёт не туда либо страница рисуется
                  скриптом (у ЕИС ровно так: карточка 44-ФЗ отдаёт оболочку портала)
    НЕ ОТКРЫЛАСЬ  код ответа или ошибка, называется прямо

Заслон на оболочку беру свой же: страница с шапкой портала и без нашей машины — не текст.
"""
import csv
import io
import json
import random
import re
import ssl
import time
import urllib.request

FAYL = r'C:\sender\_ops\PARK-SLOVAR-SERII-3S.csv'
random.seed(11)
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0.0.0 Safari/537.36')
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
op = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                 urllib.request.ProxyHandler({}))
OBOL = re.compile(r'Официальный сайт Единой информационной системы|включите JavaScript|'
                  r'Your browser is out of date|\{[a-z-]{2,20}:[^}]{2,80}\}', re.I)

rows = [r for r in csv.DictReader(io.open(FAYL, encoding='utf-8-sig'), delimiter=';')
        if (r.get('ssylki') or '').startswith('http')]
vyb = random.sample(rows, 5)

itog = []
for r in vyb:
    ser = r['seriya']
    url = (r['ssylki'].split('|')[0]).strip()
    print('\n\n===== серия %s' % ser)
    print('  ссылка: %s' % url[:130])
    try:
        h = op.open(urllib.request.Request(url, headers={'User-Agent': UA}),
                    timeout=90).read().decode('utf-8', 'replace')
        kod = 200
    except Exception as e:  # noqa: BLE001
        print('  ИСХОД: НЕ ОТКРЫЛАСЬ — %s' % str(e)[:110])
        itog.append({'seriya': ser, 'ishod': 'не открылась', 'url': url})
        time.sleep(1)
        continue
    tx = re.sub(r'<[^>]+>', ' ', re.sub(r'<script.*?</script>|<style.*?</style>', ' ', h,
                                        flags=re.S | re.I))
    tx = re.sub(r'\s+', ' ', tx)
    # обозначение ищем гибко: пробелы и дефисы не считаем
    plosk = re.sub(r'[\s\-]', '', tx).upper()
    ser_pl = re.sub(r'[\s\-]', '', ser).upper()
    est = ser_pl in plosk
    obol = bool(OBOL.search(tx[:2000]))
    mash = bool(re.search(r'компрессор|воздуходув|нагнетател|азот|кислород', tx, re.I))
    ishod = ('ДОКАЗЫВАЕТ' if est else
             ('оболочка портала, текста нет' if obol and not mash else
              'открылась, но обозначения нет'))
    print('  код %s, текст %d знаков' % (kod, len(tx)))
    print('  обозначение «%s» на странице: %s | наша машина в тексте: %s' % (ser, est, mash))
    print('  ИСХОД: %s' % ishod)
    m = re.search(r'.{0,90}%s.{0,120}' % re.escape(ser[:6]), tx, re.I)
    print('  кусок: %s' % (m.group(0)[:210] if m else tx[:180]))
    itog.append({'seriya': ser, 'ishod': ishod, 'url': url, 'znakov': len(tx)})
    time.sleep(1)

print('\n\n########## ЧИСЛА')
for i in itog:
    print('  %-16s %s' % (i['seriya'], i['ishod']))
print('  доказывают %d из %d' % (sum(1 for i in itog if i['ishod'] == 'ДОКАЗЫВАЕТ'), len(itog)))
print('ИТОГ ' + json.dumps(itog, ensure_ascii=False)[:600])
