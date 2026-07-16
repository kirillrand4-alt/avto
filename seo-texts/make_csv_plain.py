# -*- coding: utf-8 -*-
"""CSV БЕЗ микроразметки (для админа, который делает разметку сам):
столбец 1 - ссылка, столбец 2 - только текст (publish/plain/<slug>.html).
QUOTE_ALL, ';', UTF-8 BOM, ячейка в одну строку."""
import csv, json, glob, os, re

DIR = os.path.dirname(os.path.abspath(__file__))
SITE = 'https://prokompressor.ru'


def main():
    rows = []
    for pf in glob.glob(os.path.join(DIR, 'gen', 'payload-*.json')):
        slug = os.path.basename(pf)[len('payload-'):-len('.json')]
        pp = os.path.join(DIR, 'publish', 'plain', slug + '.html')
        if not os.path.exists(pp):
            continue
        p = json.load(open(pf))
        url = p.get('url', '')
        if url.startswith('/'):
            url = SITE + url
        html = re.sub(r'[\r\n]+', ' ', open(pp, encoding='utf-8').read()).strip()
        rows.append((url, html))
    rows.sort(key=lambda r: r[0])
    out = os.path.join(DIR, 'prokompressor-texts-plain.csv')
    with open(out, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f, delimiter=';', quoting=csv.QUOTE_ALL)
        w.writerow(['url', 'text_html'])
        w.writerows(rows)
    print(f'CSV (plain): {out} | строк {len(rows)}')


if __name__ == '__main__':
    main()
