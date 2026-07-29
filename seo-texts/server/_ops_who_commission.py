# -*- coding: utf-8 -*-
"""Кто оказался в закупочных комиссиях: должности как они записаны."""
import json
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

e = EDB.EnrichDB().cx


def main():
    # По source искать нельзя: add_person делает upsert по (inn, person, post),
    # и у человека, уже известного из другого источника, source остаётся
    # прежним. Ищем по ССЫЛКЕ на документ закупки и по свежести записи.
    строки = [dict(zip(('inn', 'person', 'post', 'role', 'phone', 'source_url',
                        'source', 'updated_at'), r))
              for r in e.execute(
        "SELECT inn, person, post, role, phone, source_url, source, updated_at "
        "FROM people WHERE source_url LIKE '%zakupki%' OR source LIKE '%комисс%' "
        "ORDER BY updated_at DESC LIMIT 25")]
    свежие = [dict(zip(('person', 'post', 'role', 'source', 'updated_at'), r))
              for r in e.execute(
        "SELECT person, post, role, source, updated_at FROM people "
        "ORDER BY updated_at DESC LIMIT 12")]
    роли = {}
    for x in строки:
        роли[x['role'] or '(пусто)'] = роли.get(x['role'] or '(пусто)', 0) + 1
    print(json.dumps({'всего': len(строки), 'по_ролям': роли,
                      'последние_записанные': свежие,
                      'люди': [{'фио': x['person'], 'должность': x['post'],
                                'роль': x['role'], 'тел': x['phone'],
                                'ссылка': (x['source_url'] or '')[:70]}
                               for x in строки[:20]]},
                     ensure_ascii=False, indent=1)[:4000])


if __name__ == '__main__':
    main()
