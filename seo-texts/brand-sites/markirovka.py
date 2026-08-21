#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Правила маркировки, вычисленные по нашему каталогу, а не угаданные.

    python3 markirovka.py --export <bitrix.csv> [--out markirovka.json]

ЗАЧЕМ. Владелец нашёл в ТЗ утверждение «индекс Д - признак станции
с ресивером». Неправда: у Remeza число в имени это ресивер (ВК15Е-10-500),
а Д - встроенный осушитель (ВК15Е-10-500Д). Проверка по выгрузке
подтвердила владельца на 12 748 позициях: где в имени есть Д, свойство
«осушитель» стоит в 2928 случаях против 40, то есть связь держится
на 98,7%.

База знаний тут не помогла: в brands-synthesized.json у Remeza
marking_rules = null. Модель, не имея источника, придумала правдоподобное.

Поэтому маркировку не описываем словами, а СЧИТАЕМ: берём имена позиций
и свойства из той же выгрузки и меряем, с чем коррелирует каждый токен.
Что подтвердилось на сотнях позиций - то и уходит в задание, с числами.
Что не подтвердилось - не уходит вовсе.

ЧЕГО ЭТОТ СКРИПТ НЕ ДЕЛАЕТ. Он не объясняет СМЫСЛ обозначения, только
связь с нашим свойством. «Д означает осушитель» - вывод из данных;
«Д означает Dryer от английского» - догадка, и её здесь нет.
"""
import argparse, collections, csv, json, os, re, sys

csv.field_size_limit(10 ** 7)
DIR = os.path.dirname(os.path.abspath(__file__))

# Свойства выгрузки, с которыми сверяем токены имени.
SVOYSTVA = {
    'осушитель': 'IP_PROP22565',
    'ресивер': 'IP_PROP22574',
    'частотник': 'IP_PROP22586',
    'тип смазки': 'IP_PROP22583',
    'привод': 'IP_PROP22601',
    'охлаждение': 'IP_PROP22669',
}
BREND = 'IP_PROP22553'
IMYA = 'IE_NAME'

# Бренды сетки: как пишутся в выгрузке.
NASHI = ('abac', 'atlas copco', 'berg', 'cross air', 'dali', 'ekomak',
         'enger', 'fini', 'ironmac', 'kraftmann', 'remeza', 'зиф')

# Токен - буквенный или цифровой хвост в обозначении модели. Числа
# группируем по разрядности: конкретные 200/500/1000 это объём ресивера,
# и важно не само число, а что оно вообще стоит.
TOKEN = re.compile(r'(?<![А-ЯA-Z])([А-ЯA-Z]{1,3})(?![а-яa-z])|(\d{2,4})')


def tokeny(name):
    """Токены из части имени после первого дефиса: там живут индексы."""
    hvost = name.split('-', 1)[1] if '-' in name else name
    out = set()
    for m in TOKEN.finditer(hvost):
        bukvy, chislo = m.group(1), m.group(2)
        if bukvy and len(bukvy) <= 3:
            out.add(bukvy)
        if chislo:
            out.add(f'<{len(chislo)}-значное>')
    return out


def da(v):
    return (v or '').strip().lower().startswith('да')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--export', required=True)
    ap.add_argument('--out', default=os.path.join(DIR, 'markirovka.json'))
    ap.add_argument('--min-pozitsiy', type=int, default=40,
                    help='реже - совпадение, а не правило')
    ap.add_argument('--min-svyaz', type=float, default=0.85,
                    help='доля, ниже которой связь не утверждаем')
    a = ap.parse_args()

    # счётчики: бренд -> токен -> свойство -> [есть, нет]
    schet = collections.defaultdict(
        lambda: collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0])))
    vsego = collections.Counter()
    bez = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0]))

    with open(a.export, encoding='utf-8-sig', newline='') as fh:
        for row in csv.DictReader(fh, delimiter=';'):
            b = (row.get(BREND) or '').strip().lower()
            if not any(n in b for n in NASHI):
                continue
            brend = next(n for n in NASHI if n in b)
            name = (row.get(IMYA) or '').strip()
            if not name:
                continue
            vsego[brend] += 1
            tk = tokeny(name)
            for svo, col in SVOYSTVA.items():
                est = da(row.get(col))
                for t in tk:
                    schet[brend][t][svo][0 if est else 1] += 1
                bez[brend][svo][0 if est else 1] += 1

    itog = {}
    for brend, po_tokenu in schet.items():
        pravila = []
        for token, po_svo in po_tokenu.items():
            for svo, (est, net) in po_svo.items():
                n = est + net
                if n < a.min_pozitsiy:
                    continue
                dolya = est / n
                # Фон: как часто свойство стоит у бренда вообще. Токен
                # интересен, только если он ЗАМЕТНО отличается от фона -
                # иначе мы объявим правилом то, что верно и без токена.
                fe, fn = bez[brend][svo]
                fon = fe / max(fe + fn, 1)
                if dolya < a.min_svyaz or dolya - fon < 0.25:
                    continue
                pravila.append({
                    'токен': token, 'свойство': svo,
                    'позиций с токеном': n, 'из них свойство есть': est,
                    'связь': round(dolya, 3), 'фон по бренду': round(fon, 3),
                })
        pravila.sort(key=lambda x: (-x['связь'], -x['позиций с токеном']))
        if pravila:
            itog[brend] = {'позиций в выгрузке': vsego[brend],
                           'правила': pravila[:12]}

    with open(a.out, 'w', encoding='utf-8') as fh:
        json.dump(itog, fh, ensure_ascii=False, indent=1)
        fh.flush(); os.fsync(fh.fileno())

    print(f'брендов с подтверждёнными правилами: {len(itog)}\n')
    for brend, d in sorted(itog.items()):
        print(f'{brend} ({d["позиций в выгрузке"]} позиций)')
        for p in d['правила'][:5]:
            print(f'   «{p["токен"]}» -> {p["свойство"]}: '
                  f'{p["из них свойство есть"]}/{p["позиций с токеном"]} '
                  f'= {p["связь"]:.0%}, фон {p["фон по бренду"]:.0%}')
    print(f'\n-> {a.out}')


if __name__ == '__main__':
    main()
