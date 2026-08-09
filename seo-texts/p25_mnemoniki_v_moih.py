# -*- coding: utf-8 -*-
"""Проверяю у себя дефект, найденный 1-й сессией глазами: HTML-мнемоники в полях.

Её запись: в названиях стояло `АО &quot;НАК &quot;АЗОТ&quot;` вместо кавычек, пришло из
HTML-выгрузок площадок и прошло через все вливания незамеченным — «счётчики на мнемониках
не спотыкаются, для них это обычный текст». Раскодировано 3 511 полей.

У себя я эти следы уже видела мельком и не придала значения: в цитате обратного хода стояло
`E-mail &amp;lt;KoshilevON@sibelectro.com&amp;gt;`, а в ссылке `snhz.ru/?event=zakupki&amp;za=68`.
Второе хуже первого: **мнемоника в АДРЕСЕ ломает саму ссылку** — `&amp;` вместо `&` уводит
на другую страницу или в 404, то есть доказательство перестаёт открываться.

Считаю по всем своим выложенным файлам, в каких полях и сколько, и раскодирую. Двойное
кодирование (`&amp;lt;` = сначала `<` -> `&lt;`, потом `&` -> `&amp;`) разворачиваю в цикле,
пока строка меняется, но не больше трёх раз — иначе можно съесть настоящий текст.

Числа в КОНЦЕ.
"""
import collections
import html as _html
import io
import json
import os
import re
import urllib.request

FAJLY = [r'C:\sender\_ops\park_ingest_3.jsonl', r'C:\sender\_ops\park_ingest_3b.jsonl',
         r'C:\sender\_ops\PARK-KONTAKTY-3S-CHESTNO.jsonl',
         r'C:\sender\_ops\PARK-EIS-ZAKAZCHIKI-3S.jsonl',
         r'C:\sender\_ops\PARK-OBRATNYY-PROVERENO-3S.jsonl']
MNEM = re.compile(r'&(?:amp|quot|lt|gt|nbsp|#\d{2,5}|laquo|raquo|mdash|ndash);', re.I)


def razvernut(s):
    for _ in range(3):
        n = _html.unescape(s)
        if n == s:
            break
        s = n
    return s


op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
svod, po_polyu, v_ssylkah = collections.Counter(), collections.Counter(), collections.Counter()
primery = []
for put in FAJLY:
    if not os.path.exists(put):
        svod['файла нет: %s' % os.path.basename(put)] += 1
        continue
    stroki, tronuto = [], 0
    for s in io.open(put, encoding='utf-8'):
        try:
            o = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        izm = False
        for k, v in list(o.items()):
            if not isinstance(v, str) or not MNEM.search(v):
                continue
            po_полю = po_polyu
            po_полю['%s / %s' % (os.path.basename(put), k)] += 1
            if k in ('istochniki', 'ssylka', 'zakazchik_kartochka'):
                v_ssylkah[os.path.basename(put)] += 1
            if len(primery) < 8:
                primery.append('%s / %s: %s' % (os.path.basename(put)[:26], k, v[:90]))
            o[k] = razvernut(v)
            izm = True
        if izm:
            tronuto += 1
        stroki.append(o)
    svod['%s: строк тронуто' % os.path.basename(put)] = tronuto
    if tronuto:
        with io.open(put, 'w', encoding='utf-8') as f:
            for o in stroki:
                f.write(json.dumps(o, ensure_ascii=False) + '\n')
        try:
            rq = urllib.request.Request('%s/%s' % (os.environ.get('DROP_URL', '').rstrip('/'),
                                                   os.path.basename(put)),
                                        data=io.open(put, 'rb').read(), method='PUT',
                                        headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
            op.open(rq, timeout=300).read()
        except Exception:  # noqa: BLE001
            svod['%s: НЕ ВЫЛОЖЕН' % os.path.basename(put)] += 1

print('\n\n########## ЧТО СТОЯЛО В ПОЛЯХ')
for p in primery:
    print('  ' + p)
print('\n########## ЧИСЛА')
for k, v in svod.most_common():
    print('  %-52s %6s' % (k[:52], v))
print('  --- по полям')
for k, v in po_polyu.most_common(12):
    print('     %-52s %6d' % (k[:52], v))
print('  --- МНЕМОНИКА В САМОЙ ССЫЛКЕ (ломает доказательство)')
if v_ssylkah:
    for k, v in v_ssylkah.most_common():
        print('     %-40s %6d' % (k, v))
else:
    print('     таких нет')
print('ИТОГ ' + json.dumps({'полей раскодировано': sum(po_polyu.values()),
                            'из них в ссылках': sum(v_ssylkah.values())}, ensure_ascii=False))
