# -*- coding: utf-8 -*-
"""Прогон обозначений машин по реестру ЭПБ.

Зачем отдельно от `mpb_harvest.py`: запрос по модели («К-1500-62-2») даёт **точность
вместо охвата**. Общие термины тащат насосы, паровые турбины и обвязку; обозначение
серии — это гарантированно наша машина, и вдобавок сразу известно, что именно у
предприятия стоит, а значит что предлагать на замену.

Источник обозначений — референс-лист Невского завода, 291 уникальная модель за 1947–2019.
Сам список поставок как список заказчиков не годится (97 % поставок до 2000 года,
советские названия не сводятся к нынешним юрлицам), но модели из него живут в реестре ЭПБ
под текущими владельцами.

Использование:
    python3 mpb_models.py <файл-со-списком-моделей> <out.csv> [--min-len 6]

Файл со списком — по одному обозначению в строке. Пропускаются слишком короткие
обозначения (по умолчанию < 6 знаков): «К-25» находит всё подряд, потому что поиск
полнотекстовый со стеммингом, а не по точной строке.
"""
import csv
import sys
import time

import mpb_harvest as H


def probe(model, max_pages=20):
    """Вернуть (всего_по_счётчику, список_строк) по одному обозначению."""
    import urllib.parse
    qs = {'q': model}
    url0 = f'{H.BASE}/conclusions?{urllib.parse.urlencode(qs)}'
    first = H.get(url0)
    n = H.total(first)
    if not n:
        return 0, []
    seen, recs = set(), []
    page_html, p = first, 1
    while p <= max_pages:
        got = H.rows(page_html)
        new = [r for r in got if r['nomer'] not in seen]
        for r in new:
            seen.add(r['nomer'])
        recs.extend(new)
        if len(recs) >= n or not got:
            break
        p += 1
        qs['page'] = p
        time.sleep(H.PAUSE)
        try:
            page_html = H.get(f'{H.BASE}/conclusions?{urllib.parse.urlencode(qs)}')
        except Exception as e:  # noqa: BLE001
            print(f'    стр. {p} не открылась: {e}', file=sys.stderr)
            break
    return n, recs


def main():
    if len(sys.argv) < 3:
        sys.exit('usage: mpb_models.py <models.txt> <out.csv> [--min-len N]')
    models_path, out_path = sys.argv[1], sys.argv[2]
    min_len = 6
    if '--min-len' in sys.argv:
        min_len = int(sys.argv[sys.argv.index('--min-len') + 1])

    models = []
    for line in open(models_path, encoding='utf-8'):
        m = line.strip()
        if m and len(m) >= min_len:
            models.append(m)
    print(f'обозначений к прогону: {len(models)}', file=sys.stderr)

    cols = ['model', 'srok', 'zapros', 'nomer', 'data', 'inn_zakazchika', 'zakazchik',
            'obekt', 'tip', 'inn_eo', 'ekspertnaya_org', 'vyvod', 'istochnik',
            'istochnik_zakazchik']
    f = open(out_path, 'w', encoding='utf-8-sig', newline='')
    w = csv.DictWriter(f, fieldnames=cols, delimiter=';', extrasaction='ignore')
    w.writeheader()

    H.SROK, total_rows = 'any', 0
    for i, model in enumerate(models, 1):
        H.ZAPROS = model
        try:
            n, recs = probe(model)
        except Exception as e:  # noqa: BLE001
            print(f'[{i}/{len(models)}] {model}: ОШИБКА {e}', file=sys.stderr)
            time.sleep(H.PAUSE)
            continue
        inns = {r['inn_zakazchika'] for r in recs if r['inn_zakazchika']}
        print(f'[{i}/{len(models)}] {model}: счётчик {n}, взято {len(recs)}, ИНН {len(inns)}',
              file=sys.stderr)
        for r in recs:
            r['model'] = model
            w.writerow(r)
        total_rows += len(recs)
        f.flush()
        time.sleep(H.PAUSE)

    f.close()
    print(f'итого строк: {total_rows} → {out_path}', file=sys.stderr)


if __name__ == '__main__':
    main()
