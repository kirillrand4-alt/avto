# -*- coding: utf-8 -*-
"""Полнота контактов: панель (MEYER-PISALI.csv) против нашего обхода ЦА по ОБЩИМ компаниям (ИНН есть в обоих).
Только счётчики; что пропустили — по типам (домен сайта / чужой домен / бесплатная почта) и по источнику страницы."""
import collections, csv, io, json, re

БЕСПЛ = re.compile(r'@(?:mail|inbox|list|bk|internet|yandex|ya|gmail|rambler|hotmail|outlook|icloud)\.', re.I)
пан = collections.defaultdict(set)
with io.open(r'C:\seostat\drop\drop-storage\MEYER-PISALI.csv', encoding='utf-8-sig', errors='replace') as f:
    r_ = csv.reader(f, delimiter=';')
    шапка = next(r_)
    ии = next((i for i, h in enumerate(шапка) if 'ИНН' in h.upper()), 0)
    ик = next((i for i, h in enumerate(шапка) if 'онтакт' in h), None)
    for row in r_:
        if ик is None or len(row) <= ик:
            continue
        инн = re.sub(r'\D', '', row[ии])
        for м in re.finditer(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+', row[ик]):
            пан[инн].add(м.group(0).lower())
наши, все_наши, сайт, открылся, доки = collections.defaultdict(set), collections.defaultdict(set), {}, {}, {}
for s in io.open(r'C:\sender\server\ca-kontakty.jsonl', encoding='utf-8', errors='replace'):
    try:
        з = json.loads(s)
    except ValueError:
        continue
    if з.get('итог') != 'ok':
        continue
    i = з['inn']
    наши[i] = {(x.get('почта') or '').lower() for x in з.get('номера') or [] if x.get('почта') and x.get('чей') != 'другая'}
    все_наши[i] = {(x.get('почта') or '').lower() for x in з.get('номера') or [] if x.get('почта')}
    сайт[i] = re.sub(r'^https?://(www\.)?', '', (з.get('сайт') or '').lower()).split('/')[0]
    открылся[i] = any(ст == 'ok' for _, ст in з.get('страницы') or [])
общие = [i for i in пан if i in наши]
с = collections.Counter()
пропуск = collections.Counter()
for i in общие:
    п, н = пан[i], наши[i]
    с['компаний'] += 1
    с['адресов у панели'] += len(п)
    с['адресов у нас (свои)'] += len(н)
    с['у нас больше'] += len(н) > len(п)
    с['у панели больше'] += len(п) > len(н)
    с['поровну'] += len(п) == len(н)
    с['общих адресов'] += len(п & н)
    с['сайт у нас открылся'] += открылся[i]
    for а in п - н:
        дом = а.split('@')[1]
        if а in все_наши[i]:
            пропуск['у нас помечен чужим'] += 1
        elif not открылся[i]:
            пропуск['сайт у нас не открылся'] += 1
        elif сайт[i] and (дом == сайт[i] or дом.endswith('.' + сайт[i]) or сайт[i].endswith(дом)):
            пропуск['домен сайта, но мы не нашли'] += 1
        elif БЕСПЛ.search(а):
            пропуск['бесплатная почта (не с сайта?)'] += 1
        else:
            пропуск['другой домен'] += 1
print('===ИТОГ===', json.dumps(dict(с), ensure_ascii=False))
print('пропущенные адреса панели:', json.dumps(dict(пропуск.most_common()), ensure_ascii=False))
