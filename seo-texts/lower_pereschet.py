# -*- coding: utf-8 -*-
"""Сколько строк потеряли поиски через SQL `lower()` по русским словам. Замер, а не догадка.

ОТКУДА ПУНКТ. `sqlite3.lower()` знает только латиницу: `lower('ЦЕНТРОБЕЖНЫЙ')` возвращает
`'ЦЕНТРОБЕЖНЫЙ'`, и сравнение `like '%центробежн%'` даёт ЛОЖЬ. То же и с самим LIKE — он
регистронезависим тоже только для ASCII. Значит каждый запрос вида

    where lower(coalesce(quote,'')) like '%центробежн%'

молча пропускает всё, что записано ПРОПИСНЫМИ или с прописной буквы. Ноль при этом выглядит
как «таких строк нет», а не как «прибор не смотрит в эту сторону» — и именно в таком виде я
уже принимала результаты (`skrytiya_peresmotr.py`, отбор скрытий на пересмотр).

ЧТО ЗДЕСЬ СЧИТАЕТСЯ. По каждому ходовому слову — три числа:
    SQL      сколько находит запрос как он написан сейчас;
    PYTHON   сколько находит честное сравнение с приведением регистра средствами Python;
    РАЗНИЦА  сколько строк было невидимо.
Ничего не переписывается: сперва цена ошибки, потом решение, что чинить.
"""
import json
import sqlite3

BAZA = 'file:C:/seostat/data/centrifugal.db?mode=ro'
SLOVA = ('центробежн', 'турбокомпрессор', 'нагнетател', 'турбовоздуходувк', 'воздуходувк',
         'компрессор', 'главный инженер', 'главный механик', 'главный энергетик',
         'не доказан', 'не подтвержд')


def main():
    b = sqlite3.connect(BAZA, uri=True)
    itog = {}
    for tabl, kolonki in (('fact', ('quote', 'equipment_type')),
                          ('person', ('position',)),
                          ('contact', ('position', 'role'))):
        est = [r[1] for r in b.execute('pragma table_info(%s)' % tabl)]
        for kol in kolonki:
            if kol not in est:
                itog['%s.%s' % (tabl, kol)] = 'колонки нет'
                continue
            vse = [str(r[0] or '') for r in b.execute(
                'select coalesce(%s,"") from %s' % (kol, tabl))]
            for slovo in SLOVA:
                sql = b.execute(
                    'select count(*) from %s where lower(coalesce(%s,"")) like ?'
                    % (tabl, kol), ('%' + slovo + '%',)).fetchone()[0]
                py = sum(1 for v in vse if slovo in v.lower())
                if py or sql:
                    itog['%s.%s ~ %s' % (tabl, kol, slovo)] = {
                        'SQL': sql, 'PYTHON': py, 'НЕВИДИМО': py - sql}
    poteryano = sum(v['НЕВИДИМО'] for v in itog.values()
                    if isinstance(v, dict) and v.get('НЕВИДИМО', 0) > 0)
    # ПОРЯДОК ПЕЧАТИ ОБРАТНЫЙ НАРОЧНО. Ответ раннера отдаёт `stdout_tail` — КОНЕЦ вывода, а
    # не начало. Первый прогон напечатал самые крупные потери сверху, и до меня доехали три
    # строки с нулями: «невидимо 0, невидимо 0, невидимо 0» при итоге 8 957. Правило своё же:
    # счётчики и главное — последними.
    for k, v in sorted((x for x in itog.items() if isinstance(x[1], dict)),
                       key=lambda x: x[1]['НЕВИДИМО'])[-22:]:
        print('REC %-46s SQL %6d  PYTHON %6d  НЕВИДИМО %6d'
              % (k, v['SQL'], v['PYTHON'], v['НЕВИДИМО']))
    print('ИТОГ ' + json.dumps({'НЕВИДИМО ВСЕГО': poteryano,
                                'проверок': len(itog)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
