# -*- coding: utf-8 -*-
"""Что на самом деле в 1573 предприятиях: состояние и обогащённость контактами.

Владелец спросил про «стоит/покупают/планируют» и насколько это обогащено.
Отвечать надо по СОБРАННОМУ файлу, а не по счётчикам прогона.
"""
import csv, io, os
from collections import Counter

ДРОП = r'C:\seostat\drop\drop-storage'
csv.field_size_limit(10 ** 7)


def rd(п):
    return list(csv.DictReader(io.StringIO(
        open(п, encoding='utf-8-sig', errors='replace').read()), delimiter=';'))


def main():
    сум = rd(r'C:\sender\server\SVOD-VSE-OBEDINENNYY.csv')
    оч = rd(os.path.join(ДРОП, 'OCHERED-centrobezhnye.csv'))
    сост = {(r.get('inn') or '').strip(): r for r in оч}
    print(f'предприятий: {len(сум)}')

    c = Counter()
    for r in сум:
        s = (r.get('sostoyanie_potverzhdeno_faktom') or '').strip()
        for x in (s.split(' | ') if s else ['(состояние по факту не подтверждено)']):
            c[x] += 1
    print('\n=== СОСТОЯНИЕ, доказанное фактом «центробежная + воздух» ===')
    for k, n in c.most_common():
        print(f'  {n:>5}  {k}')

    print('\n=== СРЕДА по очереди ===')
    for k, n in Counter((сост.get(r['inn'], {}).get('sreda_dokazana') or '?')
                        for r in сум).most_common():
        print(f'  {n:>5}  {k}')

    тел = поч = сайт = люди = тех = 0
    for r in сум:
        if (r.get('telefony_predpriyatiya') or '').strip():
            тел += 1
        if (r.get('pochta') or '').strip():
            поч += 1
        if (r.get('sayt') or '').strip():
            сайт += 1
        if int(r.get('lyudej_vsego') or 0):
            люди += 1
        if int(r.get('tehnicheskih') or 0):
            тех += 1
    n = len(сум)
    print('\n=== ОБОГАЩЁННОСТЬ КОНТАКТАМИ (предприятий из %d) ===' % n)
    for имя, v in (('телефон предприятия', тел), ('почта', поч), ('сайт', сайт),
                   ('хотя бы один НАЗВАННЫЙ человек', люди),
                   ('технический человек', тех)):
        print(f'  {v:>5}  ({round(100*v/n):>2}%)  {имя}')
    print(f'\n  БЕЗ ЕДИНОГО КОНТАКТА (ни телефона, ни почты, ни человека): '
          f'{sum(1 for r in сум if not((r.get("telefony_predpriyatiya") or "").strip() or (r.get("pochta") or "").strip() or int(r.get("lyudej_vsego") or 0)))}')


if __name__ == '__main__':
    main()
