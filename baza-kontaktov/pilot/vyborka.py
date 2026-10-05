# -*- coding: utf-8 -*-
"""Выборка запросов пилота XMLRiver (ТЗ-PILOT-XMLRIVER.md, п. 2).

Берёт P1-шаблоны из zaprosy.csv, подставляет регионы пилота, добавляет минус-слова
уровня [query:*] из minus_slova.txt и пишет pilot_zaprosy.csv. Каждая строка уходит
и в Яндекс, и в Google.

    python3 vyborka.py            # -> pilot_zaprosy.csv + сводка
"""
import csv
import os
import re
from collections import Counter, OrderedDict

DIR = os.path.dirname(os.path.abspath(__file__))
BAZA = os.path.dirname(DIR)

# Регионы пилота: по 2 региона приоритета 1 из regiony.csv, подходящих сегменту.
# lr — коды регионов Яндекса; ПРОВЕРИТЬ пробой из 5 запросов до массового прогона.
LR = {
    'Алтайский край': 11235, 'Ростовская область': 11029, 'Краснодарский край': 10995,
    'Ставропольский край': 11069, 'Воронежская область': 10672, 'Липецкая область': 10712,
    'Новосибирская область': 11316, 'Белгородская область': 10645,
    'Брестская область': 29632, 'Гомельская область': 29631, 'Беларусь': 149, 'Россия': 225,
}
PILOT = {
    'elevators': {'RU': ['Алтайский край', 'Ростовская область']},
    'seeds':     {'RU': ['Краснодарский край', 'Воронежская область']},
    'exporters': {'RU': ['Ростовская область', 'Краснодарский край']},
    'nuts':      {'RU': ['Краснодарский край', 'Ставропольский край']},
    'berries':   {'RU': ['Липецкая область', 'Новосибирская область'],
                  'BY': ['Брестская область', 'Гомельская область']},
    'food':      {'RU': ['Белгородская область', 'Алтайский край'],
                  'BY': ['Брестская область', 'Гомельская область']},
}
# {город} для шаблонов уровня city: города из regiony.csv внутри регионов пилота.
GOROD = {
    'Алтайский край': ['Рубцовск', 'Бийск'], 'Ростовская область': ['Азов', 'Сальск'],
    'Краснодарский край': ['Новороссийск', 'Ейск'], 'Белгородская область': ['Белгород'],
    'Брестская область': ['Пинск'], 'Гомельская область': ['Мозырь'],
}
# {культура} в род. п. — только культуры, которых нет в отдельных P1-шаблонах.
KULTURA = {
    'seeds': ['гречихи', 'овса', 'проса', 'сорго', 'люцерны', 'сахарной свёклы'],
    'exporters': ['пшеницы', 'ячменя', 'кукурузы', 'подсолнечника', 'льна', 'нута',
                  'гороха', 'чечевицы', 'рапса', 'сои'],
}
# {продукт} для пищевых — подсегменты раздела 10, которых нет в отдельных шаблонах.
PRODUKT = ['крупа', 'макароны', 'сахар', 'патока', 'растительное масло', 'хлебобулочные изделия']
LIMIT_SEG = 150


def minus_slova():
    """{сегмент|global: [операторы]} из блоков [query:*]."""
    out, cur = {}, None
    for line in open(os.path.join(BAZA, 'minus_slova.txt'), encoding='utf-8'):
        s = line.strip()
        m = re.match(r'\[(query|post):(\w+)\]', s)
        if m:
            cur = m.group(2) if m.group(1) == 'query' else None
            continue
        if cur and s and not s.startswith('#'):
            out.setdefault(cur, []).append(s)
    return out


def regiony():
    return {r['name_nom']: r for r in csv.DictReader(open(os.path.join(BAZA, 'regiony.csv'),
                                                          encoding='utf-8'))}


def build():
    mins = minus_slova()
    sabl = [r for r in csv.DictReader(open(os.path.join(BAZA, 'zaprosy.csv'), encoding='utf-8'))
            if r['priority'] == '1']
    rows = OrderedDict()

    def add(r, q, region, country):
        q = re.sub(r'\s+', ' ', q).strip()
        key = (r['segment'], q.lower(), region)
        if key in rows:
            return
        lr = LR.get(region) or LR['Беларусь' if country == 'BY' else 'Россия']
        minus = ' '.join(mins.get('global', []) + mins.get(r['segment'], []))
        rows[key] = {'segment': r['segment'], 'subsegment': r['subsegment'], 'template': r['query_template'],
                     'query': q, 'query_full': f'{q} {minus}'.strip(), 'region': region,
                     'country': country.lower(), 'lr': lr}

    for r in sabl:
        seg, t, geo = r['segment'], r['query_template'], r['geo_level']
        kults = KULTURA.get(seg, ['']) if '{культура}' in t else ['']
        prods = PRODUKT if '{продукт}' in t else ['']
        for k in kults:
            for p in prods:
                t1 = t.replace('{культура}', k).replace('{продукт}', p)
                if geo == 'none':
                    add(r, t1, 'Россия', 'RU')
                    continue
                strana = 'BY' if geo == 'by' else 'RU'
                regs = PILOT.get(seg, {}).get(strana, [])
                if '{регион}' not in t1 and '{город}' not in t1:
                    add(r, t1, 'Беларусь' if strana == 'BY' else 'Россия', strana)
                    continue
                for reg in regs:
                    if '{город}' in t1:
                        for g in GOROD.get(reg, []):
                            add(r, t1.replace('{город}', g), reg, strana)
                    else:
                        add(r, t1.replace('{регион}', reg), reg, strana)
    # потолок на сегмент
    out, cnt = [], Counter()
    for v in rows.values():
        if cnt[v['segment']] < LIMIT_SEG:
            cnt[v['segment']] += 1
            out.append(v)
    for i, v in enumerate(out, 1):
        v['qid'] = f'q{i:04d}'
    return out, cnt


if __name__ == '__main__':
    out, cnt = build()
    cols = ['qid', 'segment', 'subsegment', 'region', 'country', 'lr', 'query', 'query_full', 'template']
    with open(os.path.join(DIR, 'pilot_zaprosy.csv'), 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
        w.writeheader()
        w.writerows(out)
    print(dict(cnt), 'всего', len(out), 'на поисковик;', 2 * len(out), 'запросов в оба')
