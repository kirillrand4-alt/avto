# -*- coding: utf-8 -*-
"""Потоковая конвертация большого xlsx (inline strings) в gzip-CSV.

Лист на 387 МБ XML целиком в память не влезет и на диск его разворачивать
незачем: читаем прямо из zip по мере разбора.
"""
import csv, gzip, io, re, sys, zipfile
import xml.etree.ElementTree as ET

NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
src, dst = sys.argv[1], sys.argv[2]

z = zipfile.ZipFile(src)
name = [n for n in z.namelist() if n.startswith('xl/worksheets/sheet')][0]


def col_index(ref):
    """A1 -> 0, B1 -> 1, AA1 -> 26."""
    m = re.match(r'([A-Z]+)', ref or '')
    if not m:
        return None
    n = 0
    for ch in m.group(1):
        n = n * 26 + (ord(ch) - 64)
    return n - 1


out = gzip.open(dst, 'wt', encoding='utf-8', newline='')
w = csv.writer(out)
rows = 0
with z.open(name) as f:
    row = []
    for ev, el in ET.iterparse(f, events=('end',)):
        if el.tag == NS + 'c':
            i = col_index(el.get('r'))
            t = el.get('t')
            if t == 'inlineStr':
                node = el.find(NS + 'is')
                v = ''.join(x.text or '' for x in node.iter(NS + 't')) if node is not None else ''
            else:
                node = el.find(NS + 'v')
                v = node.text if node is not None and node.text else ''
            if i is not None:
                while len(row) < i:
                    row.append('')
                row.append(v)
            el.clear()
        elif el.tag == NS + 'row':
            w.writerow(row)
            rows += 1
            if rows % 20000 == 0:
                print('  строк:', rows, flush=True)
            row = []
            el.clear()
out.close()
print('ГОТОВО, строк:', rows)
