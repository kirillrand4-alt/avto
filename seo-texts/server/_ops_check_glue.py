# -*- coding: utf-8 -*-
"""Системна ли склейка «база одного номера + добавочный другого».

У Перхина доказано: в БД 8(8175)54-15-00 доб.0100, а на странице у него
+7(8202)67-63-07 доб.0100 — база взята из строки ПРИЁМНОЙ. Смотрим ещё 5
подозрительных: печатаем кусок страницы вокруг добавочного.
"""
import gzip
import json
import os
import re
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

e = EDB.EnrichDB().cx
КЭШ = r'C:\seostat\drop\pagecache'
ЦЕЛИ = [('7014027742', '+7 (3822) 98-15-06 доб.3-25'),
        ('6230029069', '+7(4912) 30-01-02 доб.1014'),
        ('7716182080', '+7 (8452) 309-114 доб. 1000'),
        ('4346000273', '+7 (8332) 71-12-28 доб.15-42'),
        ('2611007356', '+7 (8652) 330-470 доб.18-506')]


def текст(h):
    h = re.sub(r'(?is)<(script|style|noscript)[^>]*>.*?</\1>', ' ', h or '')
    h = re.sub(r'(?s)<[^>]+>', ' ', h)
    h = re.sub(r'&nbsp;?', ' ', h)
    for a, b in (('&amp;', '&'), ('&quot;', '"')):
        h = h.replace(a, b)
    return re.sub(r'\s+', ' ', h)


def кэш(inn):
    p = os.path.join(КЭШ, '%s.json.gz' % inn)
    if not os.path.exists(p):
        return None
    return json.loads(gzip.open(p, 'rb').read().decode('utf-8', 'replace'))


def main():
    for inn, ph in ЦЕЛИ:
        d = кэш(inn)
        if not d:
            print('%s: кэша нет' % inn)
            continue
        t = текст(''.join((p.get('html') or '') for p in d.get('pages') or []))
        доб = re.split(r'доб', ph, 1, re.I)[-1].strip(' .')
        цб = re.sub(r'\D', '', re.split(r'доб', ph, 1, re.I)[0])
        if len(цб) == 11 and цб[0] in '78':
            цб = цб[1:]
        # где на странице встречается этот добавочный
        куски = []
        for m in re.finditer(r'доб[^0-9]{0,4}' + re.escape(доб), t, re.I):
            куски.append(t[max(0, m.start() - 190):m.start() + 40])
        # где встречается база
        rxб = r'\D{0,3}'.join(цб)
        база_есть = bool(re.search(rxб, t))
        print('--- ИНН %s | БД: %s' % (inn, ph))
        print('    база_на_странице=%s добавочный_встреч=%d'
              % (база_есть, len(куски)))
        for k in куски[:2]:
            print('    ДОБ_КОНТЕКСТ: %s' % k[-230:])
    print('ГОТОВО')


if __name__ == '__main__':
    main()
