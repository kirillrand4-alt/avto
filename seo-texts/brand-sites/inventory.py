#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Инвентаризация выгрузки Битрикса -> payload для категорийных текстов.

    python3 inventory.py <nash_katalog_*.csv> [--out katalog-inventory.json]

Зачем: правило «числа только из payload» требует источника чисел. Раньше их
собирали краулером по сайту, но выгрузка даёт то же самое точнее и целиком,
включая позиции, которых на брендовых сайтах ещё нет.

Коды свойств расшифрованы сверкой с живыми карточками (BERG ВК-22 в трёх
исполнениях): производительность и мощность из выгрузки совпали с сайтом
символ в символ, цена разошлась на 3,6% за девять дней - отсюда правило
не писать точных цен в текстах.
"""
import argparse, collections, csv, json, os, re, statistics, sys

csv.field_size_limit(10 ** 7)

PROP = {
    'IP_PROP22553': 'brand',
    'IP_PROP22555': 'weight_kg',
    'IP_PROP22562': 'power_kw',
    'IP_PROP22564': 'receiver_l',
    'IP_PROP22565': 'dryer',
    'IP_PROP22571': 'flow_lmin',
    'IP_PROP22573': 'pressure_bar',
    'IP_PROP22574': 'receiver',
    'IP_PROP22583': 'lubrication',
    'IP_PROP22586': 'vfd',
    'IP_PROP22601': 'drive',
    'IP_PROP22669': 'cooling',
}

# Тип изделия по названию. Порядок важен: «сепаратор центробежный циклонный» —
# это подготовка воздуха, а не центробежный компрессор, и ловиться должен раньше.
TYPES = [
    ('separator',   r'(?i)сепаратор|циклон|маслоуловител|влагоотделител'),
    ('dryer',       r'(?i)осушител'),
    ('filter',      r'(?i)фильтр'),
    ('receiver',    r'(?i)ресивер|воздухосборник'),
    ('spare',       r'(?i)запчаст|ремкомплект|комплект для ТО|масло |ремень|муфта|клапан|картридж|фильтр-элемент'),
    ('n2',          r'(?i)генератор азота|азотн\w+ (станц|установк|генератор)'),
    ('o2',          r'(?i)генератор кислорода|кислородн\w+ (станц|установк|генератор)'),
    ('mks',         r'(?i)модульн\w+ компрессорн|МКС\b|в контейнере'),
    ('centrifugal', r'(?i)центробежн'),
    ('booster',     r'(?i)бустер|дожимн'),
    ('diesel',      r'(?i)дизельн'),
    ('petrol',      r'(?i)бензинов'),
    ('piston',      r'(?i)поршнев'),
    ('scroll',      r'(?i)спиральн'),
    ('screw',       r'(?i)винтов'),
]


def num(v):
    v = (v or '').strip().replace(',', '.').replace(' ', '')
    try:
        f = float(v)
    except ValueError:
        return None
    return f if f > 0 else None


def type_of(name):
    for t, rx in TYPES:
        if re.search(rx, name or ''):
            return t
    return 'other'


def rng(vals):
    v = sorted(x for x in vals if x is not None)
    return [v[0], v[-1]] if v else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('--out', default='katalog-inventory.json')
    ap.add_argument('--min-cards', type=int, default=3,
                    help='порог, ниже которого страницу не генерируем')
    a = ap.parse_args()

    rows = list(csv.DictReader(open(a.src, encoding='utf-8-sig', newline=''),
                               delimiter=';'))
    items = []
    for x in rows:
        if (x.get('IE_ACTIVE') or '').strip() != 'Y':
            continue
        d = {v: (x.get(k) or '').strip() for k, v in PROP.items()}
        d['name'] = (x.get('IE_NAME') or '').strip()
        d['url'] = (x.get('URL') or '').strip()
        d['price'] = num(x.get('ЦЕНА'))
        for f in ('power_kw', 'pressure_bar', 'flow_lmin', 'receiver_l', 'weight_kg'):
            d[f] = num(d[f])
        d['type'] = type_of(d['name'])
        items.append(d)

    agg = collections.defaultdict(list)
    for d in items:
        if d['brand']:
            agg[(d['brand'], d['type'])].append(d)

    out = []
    for (b, t), v in sorted(agg.items()):
        prices = [d['price'] for d in v if d['price']]
        out.append(dict(
            brand=b, type=t, n=len(v),
            power_kw=rng(d['power_kw'] for d in v),
            pressure_bar=rng(d['pressure_bar'] for d in v),
            flow_lmin=rng(d['flow_lmin'] for d in v),
            receiver_l=rng(d['receiver_l'] for d in v),
            priced=len(prices),
            price_min=min(prices) if prices else None,
            price_median=round(statistics.median(prices)) if prices else None,
            oilfree=sum(1 for d in v if d['lubrication'] == 'безмасляный'),
            vfd=sum(1 for d in v if d['vfd'] == 'да'),
            with_receiver=sum(1 for d in v if d['receiver'] == 'да'),
            with_dryer=sum(1 for d in v if d['dryer'] == 'да'),
            drive=dict(collections.Counter(d['drive'] for d in v if d['drive'])),
            enough=len(v) >= a.min_cards,
        ))

    out.sort(key=lambda r: (r['brand'], -r['n']))
    json.dump(out, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    tot = collections.Counter()
    for r in out:
        tot[r['type']] += r['n']
    print(f'позиций активных {len(items)}, пар бренд-тип {len(out)}, '
          f'из них ниже порога {sum(1 for r in out if not r["enough"])}')
    print('\nпо типам изделий:')
    for t, n in tot.most_common():
        print(f'  {t:14s} {n:6d}')
    print('\nсохранено:', a.out)


if __name__ == '__main__':
    main()
