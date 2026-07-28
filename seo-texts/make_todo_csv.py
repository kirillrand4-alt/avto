# -*- coding: utf-8 -*-
"""CSV БЕЗ микроразметки только для страниц, куда текст не встал.

Формат совпадает с prokompressor-texts-plain.csv: url;text_html, QUOTE_ALL,
';', UTF-8 BOM, ячейка в одну строку. Источник — publish/plain/<slug>.html
(сверено с gen/result-*.json, это последняя версия текстов).

В колонке url — КОНЕЧНЫЙ живой адрес страницы: там, где исходный URL
301-редиректит, подставлен адрес, на который редирект ведёт.

Выход:
  check-published-todo-plain.csv     — готово к импорту (свои URL живые);
  check-published-todo-redirect.csv  — исходный URL схлопнут 301-м; вынесено
                                       отдельно, т.к. все они ведут на ОДНУ
                                       страницу и импортировать их пачкой
                                       нельзя — нужно выбрать один текст.
"""
import csv, json, os, re

DIR = os.path.dirname(os.path.abspath(__file__))
CHECK = os.path.join(DIR, 'check-published.jsonl')
TODO = os.path.join(DIR, 'check-published-todo.csv')
PLAIN = os.path.join(DIR, 'publish', 'plain')
OUT_MAIN = os.path.join(DIR, 'check-published-todo-plain.csv')
OUT_RED = os.path.join(DIR, 'check-published-todo-redirect.csv')


def cell(slug):
    """Текст блока в одну строку — как в make_csv_plain.py."""
    with open(os.path.join(PLAIN, slug + '.html'), encoding='utf-8') as f:
        return re.sub(r'[\r\n]+', ' ', f.read()).strip()


def writer(f):
    return csv.writer(f, delimiter=';', quoting=csv.QUOTE_ALL)


def main():
    check = {}
    with open(CHECK, encoding='utf-8') as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                check[r['slug']] = r

    with open(TODO, encoding='utf-8-sig') as f:
        todo = list(csv.DictReader(f, delimiter=';'))

    main_rows, red_rows = [], []
    for t in todo:
        slug = t['slug']
        r = check[slug]
        if r.get('redirected'):
            red_rows.append((r['url'], r['final_url'], cell(slug)))
        else:
            main_rows.append((r['final_url'] or r['url'], cell(slug)))

    main_rows.sort(key=lambda x: x[0])
    red_rows.sort(key=lambda x: x[0])

    with open(OUT_MAIN, 'w', encoding='utf-8-sig', newline='') as f:
        w = writer(f)
        w.writerow(['url', 'text_html'])
        w.writerows(main_rows)
    with open(OUT_RED, 'w', encoding='utf-8-sig', newline='') as f:
        w = writer(f)
        w.writerow(['url_iskhodnyy_301', 'url_konechnyy', 'text_html'])
        w.writerows(red_rows)

    # контроль: дублей url в импортном файле быть не должно
    urls = [u for u, _ in main_rows]
    dup = {u for u in urls if urls.count(u) > 1}
    print(f'{OUT_MAIN}: {len(main_rows)} строк, дублей url: {len(dup)}')
    print(f'{OUT_RED}: {len(red_rows)} строк, '
          f'уникальных конечных адресов: {len({d for _, d, _ in red_rows})}')


if __name__ == '__main__':
    main()
