# -*- coding: utf-8 -*-
"""CSV для импорта: столбец 1 - ссылка (полный URL), столбец 2 - текст С МИКРОРАЗМЕТКОЙ
(schema-вариант: HTML + JSON-LD). Каждая ячейка в одну строку (переводы строк убраны),
QUOTE_ALL и UTF-8 BOM - корректно открывается в Excel и импортируется в 1С-Битрикс.
Источник текста: publish/schema/<slug>.html (собран build_schema.py после постфиксов)."""
import csv, json, glob, os, re

DIR = os.path.dirname(os.path.abspath(__file__))
SITE = 'https://prokompressor.ru'


def main():
    rows = []
    for pf in glob.glob(os.path.join(DIR, 'gen', 'payload-*.json')):
        slug = os.path.basename(pf)[len('payload-'):-len('.json')]
        sp = os.path.join(DIR, 'publish', 'schema', slug + '.html')
        if not os.path.exists(sp):
            continue
        p = json.load(open(pf))
        url = p.get('url', '')
        if url.startswith('/'):
            url = SITE + url
        html = open(sp, encoding='utf-8').read()
        html = re.sub(r'[\r\n]+', ' ', html).strip()      # ячейка в одну строку
        rows.append((url, html))
    rows.sort(key=lambda r: r[0])
    out = os.path.join(DIR, 'prokompressor-texts-schema.csv')
    with open(out, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f, delimiter=';', quoting=csv.QUOTE_ALL)
        w.writerow(['url', 'text_html_schema'])
        w.writerows(rows)
    print(f'CSV: {out} | строк {len(rows)}')


if __name__ == '__main__':
    main()
