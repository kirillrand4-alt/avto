# -*- coding: utf-8 -*-
"""Факты, где среда названа ПРЯМО У МАШИНЫ и она не воздух — на отзыв.

Владелец показал карточку с фактом «Закупка гелиевого компрессора» и сказал: «воздушные
нужны». Факт мой — он приехал с моего обхода ЭТП ГПБ. Значит это не претензия к панели,
а мой мусор, и снимать его мне.

ПОЧЕМУ ПРАВИЛО УЗКОЕ. Первая версия искала слова «гелий/азот/кислород» ГДЕ УГОДНО в цитате
и дала 54 строки, из которых больше половины — свои же воздушные машины:

    «Воздушный компрессор К-3000-63-1 … площадка кислородной станции № 2»   ← машина ВОЗДУШНАЯ
    «Поставка воздуходувки декарбонизатора»                                 ← машина ВОЗДУШНАЯ

Слово чужой среды стоит в описании МЕСТА, а не машины. Поэтому смотрим ровно одно слово —
прилагательное непосредственно перед словом машины: «гелиевого компрессора», «азотной
компрессорной», «газового нагнетателя». Тогда «кислородная станция» рядом с воздушным
компрессором больше не срабатывает.

ЧЕГО ПРАВИЛО НЕ ДЕЛАЕТ. Оно не решает за продавца: «холодильный компрессор» на предприятии
может стоять рядом с воздушным, и предприятие остаётся целью. Снимается ФАКТ как
доказательство воздушной машины, а не предприятие.

Использование:
    python3 chuzhaya_sreda.py            # посмотреть числа
    python3 chuzhaya_sreda.py --fajl     # выложить список на отзыв
"""
import csv
import os
import re
import sys
from collections import Counter

csv.field_size_limit(10 ** 7)
BAZA = os.path.dirname(os.path.abspath(__file__))
C = os.path.join(BAZA, 'engineers-lens', 'centro')

MASHINA = r'(?:компрессор\w*|турбокомпрессор\w*|воздуходувк\w*|нагнетател\w*|' \
          r'компрессорн\w+\s+(?:установк\w*|станци\w*))'
CHUZHAYA = (r'гелиев\w*|азотн\w*|кислородн\w*|аммиачн\w*|водородн\w*|фреонов\w*|углекислотн\w*|'
            r'метанов\w*|пропанов\w*|этиленов\w*|газов\w*|газоперекачивающ\w*|холодильн\w*|'
            r'хладагент\w*|сероводородн\w*|биогазов\w*')
PRYAMO = re.compile(rf'\b({CHUZHAYA})\s+{MASHINA}', re.I)

ISTOCHNIKI = [
    ('etpgpb-po-slovam.csv', 'predmet', 'ЭТП ГПБ, поиск по словам'),
    ('etpgpb-po-kompaniyam.csv', 'predmet', 'ЭТП ГПБ, по компаниям'),
    ('roseltorg-po-kompaniyam.csv', 'predmet', 'Росэлторг'),
    ('tektorg-po-kompaniyam.csv', 'predmet', 'ТЭК-Торг'),
    ('portal-po-kompaniyam-inn.csv', 'predmet', 'Портал Москвы'),
    ('rts-po-kompaniyam.csv', 'predmet', 'РТС-тендер'),
]
COLS = ['inn', 'predpriyatie', 'ploshchadka', 'nomer_procedury', 'chto_nashli', 'predmet',
        'ssylka', 'chto_delat']


def main():
    vsego, najdeno, out = 0, 0, []
    frazy = Counter()
    for fajl, pole, imya in ISTOCHNIKI:
        put = os.path.join(C, fajl)
        if not os.path.exists(put):
            continue
        rows = list(csv.DictReader(open(put, encoding='utf-8-sig'), delimiter=';'))
        vsego += len(rows)
        n = 0
        for r in rows:
            m = PRYAMO.search(r.get(pole) or '')
            if not m:
                continue
            n += 1
            frazy[m.group(0).lower()] += 1
            out.append({'inn': r.get('inn') or '', 'predpriyatie': (r.get('predpriyatie')
                        or r.get('zakazchik') or '')[:70], 'ploshchadka': imya,
                        'nomer_procedury': r.get('nomer') or r.get('procedure_id') or '',
                        'chto_nashli': m.group(0), 'predmet': (r.get(pole) or '')[:220],
                        'ssylka': r.get('ssylka') or '',
                        'chto_delat': 'снять как доказательство воздушной машины'})
        najdeno += n
        print(f'{imya:24} строк {len(rows):>7}  чужая среда у машины: {n}', file=sys.stderr)
    print(f'\nВСЕГО: строк {vsego}, на отзыв {najdeno}, предприятий '
          f'{len({r["inn"] for r in out})}', file=sys.stderr)
    for f, n in frazy.most_common(12):
        print(f'  {n:>4}  {f}', file=sys.stderr)
    if '--fajl' in sys.argv:
        p = os.path.join(C, 'OTZYV-2s-CHUZHAYA-SREDA-fakty.csv')
        w = csv.DictWriter(open(p, 'w', encoding='utf-8-sig', newline=''),
                           fieldnames=COLS, delimiter=';', extrasaction='ignore')
        w.writeheader()
        w.writerows(out)
        print(f'→ {p}', file=sys.stderr)


if __name__ == '__main__':
    main()
