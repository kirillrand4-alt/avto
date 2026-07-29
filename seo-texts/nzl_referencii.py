# -*- coding: utf-8 -*-
"""Разбор отраслевых референс-листов Невского завода в CSV.

Зачем. По компрессорному листу уже видно, что список почти весь советский (97 % поставок
до 2000 года) и как список заказчиков не годится. Но отраслевые листы охватывают **всё
оборудование**, а не только компрессоры, и главное — там другие годы: ГПА-32 идут
2009–2020, ЭГПА 1986–2019. Свежие поставки означают живого заказчика с известной машиной.

Строка листа выглядит как «Заказчик Объект Год Мощность Отрасль Среда», разделители
плавают, поэтому разбор идёт по годам: год — единственное надёжно опознаваемое поле.

Использование:
    python3 nzl_referencii.py <каталог-с-pdf> <out.csv>
"""
import csv
import os
import re
import sys

from pypdf import PdfReader

GOD = re.compile(r'\b(19[4-9]\d|20[0-2]\d)\b')


def stroki(path):
    r = PdfReader(path)
    for i, p in enumerate(r.pages, 1):
        t = p.extract_text() or ''
        for line in t.split('\n'):
            line = re.sub(r'\s+', ' ', line).strip()
            if len(line) > 8:
                yield i, line


def main():
    if len(sys.argv) < 3:
        sys.exit('usage: nzl_referencii.py <каталог> <out.csv>')
    src, out = sys.argv[1], sys.argv[2]
    files = sorted(f for f in os.listdir(src) if f.lower().endswith('.pdf'))
    rows = []
    for f in files:
        n = 0
        for stranica, line in stroki(os.path.join(src, f)):
            gody = GOD.findall(line)
            if not gody:
                continue
            # заказчик — то, что до первого года; хвост оставляем целиком, он разный по листам
            i = line.find(gody[0])
            zak = line[:i].strip(' .,;-')
            hvost = line[i:].strip()
            if len(zak) < 3:
                continue
            rows.append({'list': f, 'stranica': stranica, 'zakazchik': zak,
                         'god_min': min(gody), 'god_max': max(gody), 'hvost': hvost[:220]})
            n += 1
        print(f'  {f}: строк с годом {n}', file=sys.stderr)
    with open(out, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=['list', 'stranica', 'zakazchik', 'god_min',
                                           'god_max', 'hvost'], delimiter=';')
        w.writeheader()
        w.writerows(rows)
    print(f'итого {len(rows)} строк → {out}', file=sys.stderr)


if __name__ == '__main__':
    main()
