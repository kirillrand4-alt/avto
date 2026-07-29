# -*- coding: utf-8 -*-
"""Свежесть патентов: автор из патента 1997 года как ЛПР сегодня бесполезен.

Берём все «свои» патенты обоих потоков и вытаскиваем год публикации.
"""
import io
import json
import os
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, r'C:\sender\server')
sys.path.insert(0, r'C:\sender\_ops')
sys.argv = [sys.argv[0]]
import enrich_contacts as EC     # noqa: E402

ссылки = []
for п in (r'C:\sender\_ops\pat_patents.jsonl', r'C:\sender\_ops\pat_dobor.jsonl'):
    if not os.path.exists(п):
        continue
    for ln in io.open(п, encoding='utf-8', errors='replace'):
        try:
            x = json.loads(ln)
        except Exception:  # noqa: BLE001
            continue
        for u in (x.get('свои_патенты') or []):
            ссылки.append((x['имя'], u))
видели, чист = set(), []
for имя, u in ссылки:
    if u not in видели:
        видели.add(u)
        чист.append((имя, u))
print('своих патентов всего:', len(чист))

_ГОД = re.compile(r'публикация патента:\s*\d{2}\.\d{2}\.(\d{4})', re.I)
_ГОД2 = re.compile(r'подача заявки:\s*(\d{4})', re.I)


def год(пара):
    имя, u = пара
    try:
        h, _m, _ = EC._fetch_site(u)
        t = EC._текст(h or '')
    except Exception:  # noqa: BLE001
        return имя, u, 0
    m = _ГОД.search(t) or _ГОД2.search(t)
    return имя, u, int(m.group(1)) if m else 0


with ThreadPoolExecutor(max_workers=8) as п:
    итог = list(п.map(год, чист))

c = Counter()
для_печати = []
for имя, u, г in итог:
    c[(г // 10) * 10 if г else 0] += 1
    для_печати.append((г, имя, u))
для_печати.sort(reverse=True)
print('### по десятилетиям')
for д in sorted(c, reverse=True):
    print('  %s: %d' % ('%ss' % д if д else 'год не определён', c[д]))
print('### самые свежие')
for г, имя, u in для_печати[:10]:
    print('  %s | %-34s | %s' % (г, имя[:34], u))
свежих = sum(n for д, n in c.items() if д >= 2010)
всего = sum(c.values())
print('ИТОГ: патентов %d, из них 2010-х и новее %d (%.0f%%), '
      'до 2010 %d' % (всего, свежих, 100.0 * свежих / max(1, всего),
                      всего - свежих - c.get(0, 0)))
