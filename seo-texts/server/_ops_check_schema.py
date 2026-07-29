# -*- coding: utf-8 -*-
"""Разведка: схема people/phone_contacts/companies и распределение источников.

Печатаем компактно и в конце — stdout приходит хвостом.
"""
import json
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

e = EDB.EnrichDB().cx


def cols(t):
    return [r[1] for r in e.execute('PRAGMA table_info(%s)' % t).fetchall()]


def main():
    print('COLS people:', ','.join(cols('people')))
    print('COLS phone_contacts:', ','.join(cols('phone_contacts')))
    print('COLS companies:', ','.join(cols('companies')))
    print('N people =', e.execute('SELECT COUNT(*) FROM people').fetchone()[0])
    rows = e.execute(
        'SELECT source, COUNT(*), COUNT(DISTINCT inn) FROM people '
        'GROUP BY source ORDER BY 2 DESC').fetchall()
    print('PEOPLE_SOURCE:')
    for r in rows:
        print('  %-28s строк=%-6s компаний=%s' % (r[0], r[1], r[2]))


if __name__ == '__main__':
    main()
