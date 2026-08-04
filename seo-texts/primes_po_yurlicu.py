# -*- coding: utf-8 -*-
"""Примесь по ЮРЛИЦУ: мёртвые компании и факты старше самой компании.

Претензия 3-й сессии, дословно: «наша чистка по типу машины НЕ ВИДИТ примеси по юрлицу —
435 из 1 486 под подозрением: 157 мёртвых юрлиц (133 ликвидировано, 20 банкрот), 194
образованы позже факта». Проверяется здесь по нашим данным, а не принимается на слово.

ДВА РАЗНЫХ ДЕФЕКТА, и путать их нельзя:
  1. **Мёртвое юрлицо.** Компания ликвидирована или в банкротстве. Факт о её компрессоре
     может быть верным, но продавать ей некому. Это не ошибка данных — это негодная цель.
  2. **Факт СТАРШЕ компании.** Дата факта раньше даты регистрации юрлица. Такой факт
     физически не может принадлежать этой компании: значит ИНН привязан неверно —
     скорее всего, факт достался от предшественника или совпало название.
Первое чистит очередь, второе чистит ФАКТЫ. Второе опаснее: оно врёт о том, что мы знаем.

Источник по юрлицам — `ochered-egrul.csv` (ЕГРЮЛ через DaData, 833 строки, статус и
руководитель). Модуль ничего не удаляет: он считает и выкладывает список на решение.

Использование:
    python3 primes_po_yurlicu.py
"""
import csv
import os
import re
import sys
from collections import Counter

csv.field_size_limit(10 ** 7)
BAZA = os.path.dirname(os.path.abspath(__file__))
L = os.path.join(BAZA, 'engineers-lens')
C = os.path.join(L, 'centro')
OCHERED = os.path.join(L, 'OCHERED-centrobezhnye.csv')
EGRUL = os.path.join(C, 'ochered-egrul.csv')
SVOD = os.path.join(L, 'SVOD-tri-sostoyaniya.csv')
VYHOD = os.path.join(C, 'PRIMES-po-yurlicu.csv')
MERTVYE = ('LIQUIDAT', 'BANKRUPT', 'REORGANIZ')


def chitat(put):
    return list(csv.DictReader(open(put, encoding='utf-8-sig'), delimiter=';')) \
        if os.path.exists(put) else []


def god(s):
    m = re.search(r'(19|20)\d{2}', str(s or ''))
    return int(m.group(0)) if m else 0


def main():
    egrul = {r['inn']: r for r in chitat(EGRUL) if r.get('inn')}
    och = chitat(OCHERED)
    fakty = chitat(SVOD)
    if not egrul or not och:
        sys.exit('ОСТАНОВКА: нет ЕГРЮЛ или очереди')
    print(f'очередь {len(och)}, ЕГРЮЛ {len(egrul)}, фактов {len(fakty)}', file=sys.stderr)

    statusy = Counter((egrul.get(r['inn']) or {}).get('status') or 'нет в ЕГРЮЛ' for r in och)
    print('статусы предприятий очереди:', statusy.most_common(), file=sys.stderr)

    stroki = []
    sch = Counter()
    for r in och:
        e = egrul.get(r['inn']) or {}
        st = (e.get('status') or '').upper()
        mertvo = any(m in st for m in MERTVYE)
        if mertvo:
            sch['мёртвое юрлицо'] += 1
            stroki.append({'inn': r['inn'], 'predpriyatie': r.get('predpriyatie') or '',
                           'chto': 'мёртвое юрлицо', 'status': e.get('status') or '',
                           'podrobnee': 'продавать некому, цель негодная',
                           'lyudej_tehnicheskih': r.get('lyudej_tehnicheskih') or '',
                           'lyudej_s_telefonom': r.get('lyudej_s_telefonom') or ''})
        elif not e:
            sch['нет в ЕГРЮЛ'] += 1
            stroki.append({'inn': r['inn'], 'predpriyatie': r.get('predpriyatie') or '',
                           'chto': 'нет в ЕГРЮЛ', 'status': '',
                           'podrobnee': 'ИНН не подтверждён справочником',
                           'lyudej_tehnicheskih': r.get('lyudej_tehnicheskih') or '',
                           'lyudej_s_telefonom': r.get('lyudej_s_telefonom') or ''})

    # Факт старше компании проверяем только там, где у ЕГРЮЛ есть дата регистрации.
    pole_daty = None
    for k in ('data_registracii', 'registration_date', 'ogrn_date', 'data'):
        if egrul and k in next(iter(egrul.values())):
            pole_daty = k
            break
    if pole_daty:
        for f in fakty:
            e = egrul.get(f.get('inn') or '')
            if not e:
                continue
            gf, gr = god(f.get('data_fakta')), god(e.get(pole_daty))
            if gf and gr and gf < gr:
                sch['факт СТАРШЕ компании'] += 1
    else:
        print('ВНИМАНИЕ: в ЕГРЮЛ-файле нет колонки с датой регистрации — проверку «факт '
              'старше компании» выполнить НЕЧЕМ. Это не «нарушений нет», это НЕ ПРОВЕРЕНО.',
              file=sys.stderr)
        sch['проверка «факт старше компании» НЕ ВЫПОЛНЕНА'] = 1

    with open(VYHOD, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=['inn', 'predpriyatie', 'chto', 'status',
                                           'podrobnee', 'lyudej_tehnicheskih',
                                           'lyudej_s_telefonom'],
                           delimiter=';', extrasaction='ignore')
        w.writeheader()
        w.writerows(stroki)
    print('\n=== ПРИМЕСЬ ПО ЮРЛИЦУ ===', file=sys.stderr)
    for k, v in sch.most_common():
        print(f'  {k}: {v}', file=sys.stderr)
    # Отдельно: сколько из подозрительных уже дали нам людей — их терять жальче всего
    s_lyudmi = sum(1 for x in stroki if (x['lyudej_tehnicheskih'] or '0') not in ('', '0'))
    print(f'  из них уже дали технических людей: {s_lyudmi}', file=sys.stderr)
    print(f'→ {VYHOD}', file=sys.stderr)


if __name__ == '__main__':
    main()
