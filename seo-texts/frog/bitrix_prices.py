# -*- coding: utf-8 -*-
"""Пострановые чеки из битрикс-выгрузки: товар -> цена (props 22704/22705) ->
категория (IC_GROUP0-2) + бренд (22554/22553). Итог: frog/bitrix-prices.json
(медианы по категориям и бренд+категория) - точнее сегментных медиан прайса."""
import csv, json, os, re, statistics, sys

DIR = os.path.dirname(os.path.abspath(__file__))
SRC = '/tmp/claude-0/-home-user-avto/bcce55cd-293a-515c-9700-ae71a77daa5a/scratchpad/bitrix/export_file_2ov3pw9ju90trsle.csv'
csv.field_size_limit(10 ** 9)


def parse_num(v):
    s = (v or '').replace('\xa0', '').replace(' ', '').replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return None


def main():
    f = open(SRC, encoding='utf-8-sig', errors='replace', newline='')
    r = csv.reader(f, delimiter=';')
    hdr = next(r)
    idx = {h: i for i, h in enumerate(hdr)}
    c_id, c_code, c_act = idx['IE_ID'], idx['IE_CODE'], idx['IE_ACTIVE']
    c_pmin, c_pmax = idx['IP_PROP22704'], idx['IP_PROP22705']
    c_brand1, c_brand2 = idx['IP_PROP22554'], idx['IP_PROP22553']
    c_g0, c_g1, c_g2 = idx['IC_GROUP0'], idx['IC_GROUP1'], idx['IC_GROUP2']

    prods = {}                       # IE_ID -> dict (битрикс дублирует строки на мультизначения)
    for row in r:
        if len(row) <= c_g2:
            continue
        pid = row[c_id].strip()
        if not pid:
            continue
        p = prods.setdefault(pid, dict(code='', brand='', price=None, cats=None, active='Y'))
        if row[c_code].strip():
            p['code'] = row[c_code].strip()
        if row[c_act].strip():
            p['active'] = row[c_act].strip()
        if not p['brand']:
            p['brand'] = (row[c_brand1].strip() or row[c_brand2].strip()).lower()
        if p['price'] is None:
            pmin, pmax = parse_num(row[c_pmin]), parse_num(row[c_pmax])
            cand = [x for x in (pmin, pmax) if x and 500 <= x <= 300_000_000]
            if cand:
                p['price'] = sum(cand) / len(cand)
        if p['cats'] is None and row[c_g0].strip():
            p['cats'] = [row[c_g0].strip(), row[c_g1].strip(), row[c_g2].strip()]

    priced = {k: v for k, v in prods.items()
              if v['price'] and v['active'] == 'Y' and v['cats']}
    print(f'товаров: {len(prods)}, активных с ценой и категорией: {len(priced)}', flush=True)

    by_cat, by_brand_cat = {}, {}
    for v in priced.values():
        for depth in (1, 2, 3):
            key = ' / '.join(x for x in v['cats'][:depth] if x)
            by_cat.setdefault(key, []).append(v['price'])
            if v['brand']:
                by_brand_cat.setdefault(v['brand'] + ' | ' + key, []).append(v['price'])

    def med(d, min_n=3):
        return {k: dict(n=len(v), median=round(statistics.median(v)))
                for k, v in d.items() if len(v) >= min_n}

    json.dump(dict(by_cat=med(by_cat), by_brand_cat=med(by_brand_cat)),
              open(os.path.join(DIR, 'bitrix-prices.json'), 'w'), ensure_ascii=False, indent=1)
    top = sorted(med(by_cat).items(), key=lambda kv: -kv[1]['n'])[:25]
    for k, v in top:
        print(f"{v['n']:>6} | {v['median']:>12,} | {k[:70]}")


if __name__ == '__main__':
    main()
