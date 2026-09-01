# -*- coding: utf-8 -*-
"""Плоская выгрузка Битрикса: bitrix-export-full.tar.gz -> products.jsonl.gz.

В исходном CSV один товар размазан по нескольким строкам (множественные свойства),
здесь он схлопывается в один JSON-объект: скаляр или список значений.

    bash server/drop_client.sh down bitrix-export-full.tar.gz
    tar xzOf bitrix-export-full.tar.gz | python3 extract_products.py
"""
import csv, sys, json, gzip

csv.field_size_limit(10**9)

# тяжёлые и бесполезные для фасетного анализа колонки
SKIP = {'IE_PREVIEW_TEXT', 'IE_DETAIL_TEXT', 'IE_PREVIEW_TEXT_TYPE', 'IE_DETAIL_TEXT_TYPE',
        'IE_PREVIEW_PICTURE', 'IE_DETAIL_PICTURE', 'IP_PROP22551', 'IP_PROP22552',
        'IP_PROP22547', 'IP_PROP22548', 'IP_PROP22550', 'IE_TAGS'}

rdr = csv.reader(sys.stdin, delimiter=';')
header = [h.lstrip('﻿') for h in next(rdr)]
n = len(header)
keep = [i for i, h in enumerate(header) if h not in SKIP]
ID = header.index('IE_ID')

out = gzip.open('products.jsonl.gz', 'wt', encoding='utf-8')
cur_id, cur, rows, prod = None, None, 0, 0

def flush():
    global prod
    prod += 1
    rec = {}
    for i in keep:
        if cur[i]:
            v = sorted(cur[i])
            rec[header[i]] = v[0] if len(v) == 1 else v
    out.write(json.dumps(rec, ensure_ascii=False) + '\n')

for row in rdr:
    rows += 1
    if len(row) < n:
        row += [''] * (n - len(row))
    if row[ID] != cur_id:
        if cur is not None:
            flush()
        cur_id = row[ID]
        cur = [set() for _ in range(n)]
    for i in keep:
        v = row[i].strip()
        if v:
            cur[i].add(v)
    if rows % 100000 == 0:
        print(f'{rows} строк / {prod} товаров', file=sys.stderr)
if cur is not None:
    flush()
out.close()
print(f'ИТОГО строк {rows}, товаров {prod}', file=sys.stderr)
