# -*- coding: utf-8 -*-
"""Где именно теряются 338 целей с сайтом: ОКВЭД, спорный домен или что-то ещё.

Обход подразделений отобрал 57 целей, хотя подтверждённый сайт есть у 395.
Разница в 338 — не свойство мира, а фильтр `цели()`: он берёт только ОКВЭД
10–33. Здесь мерю поштучно, чтобы не гадать.
"""
import csv
import io
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB       # noqa: E402
import enrich_contacts as EC  # noqa: E402

ДРОП = r'C:\seostat\drop\drop-storage'


def main():
    csv.field_size_limit(10 ** 7)
    инны = []
    for r in csv.DictReader(io.StringIO(open(
            os.path.join(ДРОП, 'BEZ-TEHLPR-1486.csv'),
            encoding='utf-8-sig', errors='replace').read()), delimiter=';'):
        и = (r.get('inn') or '').strip()
        if и:
            инны.append(и)
    инны = list(dict.fromkeys(инны))

    cx = EDB.EnrichDB().cx
    # спорные домены считаем по ВСЕЙ таблице, как это делает обход
    по_дом = {}
    for i, s in cx.execute(
            "SELECT inn,site FROM companies WHERE COALESCE(site,'')<>''"):
        d = EC.site_domain(s)
        if d:
            по_дом.setdefault(d, set()).add(i)
    спорный = {d for d, s in по_дом.items() if len(s) > 1}

    итог = Counter()
    оквэд_отсев = Counter()
    примеры = []
    for и in инны:
        q = cx.execute("SELECT site,okved,name,COALESCE(is_competitor,0) "
                       "FROM companies WHERE inn=?", (и,)).fetchone()
        if not q or not (q[0] or '').strip():
            итог['без сайта в базе'] += 1
            continue
        if q[3]:
            итог['помечен конкурентом'] += 1
            continue
        d = EC.site_domain(q[0])
        if not d:
            итог['сайт есть, домен не разобрался'] += 1
            continue
        if d in спорный:
            итог['домен делят два ИНН'] += 1
            continue
        m = re.match(r'\s*(\d{1,2})', str(q[1] or ''))
        if not (m and 10 <= int(m.group(1)) <= 33):
            итог['отсеян ОКВЭДом'] += 1
            гр = (m.group(1) if m else 'пусто')
            оквэд_отсев[гр] += 1
            if len(примеры) < 12:
                примеры.append({'inn': и, 'okved': q[1], 'name': (q[2] or '')[:44],
                                'site': q[0][:40]})
            continue
        итог['проходит в обход'] += 1

    print(json.dumps({
        'целей': len(инны),
        'разбор': итог.most_common(),
        'какие_ОКВЭД_отсеклись': оквэд_отсев.most_common(20),
        'примеры_отсеянных': примеры,
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
