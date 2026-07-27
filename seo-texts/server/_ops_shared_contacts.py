# -*- coding: utf-8 -*-
"""Общие контакты: один телефон/ФИО на много ИНН (централизованные закупки)."""
import json
import re
import sqlite3

DB = r'C:\sender\enrich.db'


def norm(p):
    d = re.sub(r'\D', '', str(p or ''))
    if len(d) == 11 and d[0] in '78':
        d = d[1:]
    return d if len(d) == 10 else None


def main():
    cx = sqlite3.connect(f'file:{DB}?mode=ro', uri=True, timeout=60)
    out = {}

    # телефоны, встречающиеся у нескольких ИНН
    by_phone = {}
    for inn, phone, person, role, source, url in cx.execute(
            'select inn, phone, person, role, source, source_url from phone_contacts'):
        n = norm(phone)
        if not n:
            continue
        rec = by_phone.setdefault(n, {'инн': set(), 'фио': set(), 'источники': set(),
                                      'пример_url': url})
        rec['инн'].add(inn)
        if person:
            rec['фио'].add(person)
        if source:
            rec['источники'].add(source)

    shared = [(n, r) for n, r in by_phone.items() if len(r['инн']) > 1]
    shared.sort(key=lambda x: -len(x[1]['инн']))
    out['телефонов_всего'] = len(by_phone)
    out['общих_телефонов'] = len(shared)
    out['топ_общих'] = [{
        'телефон': f'+7 ({n[:3]}) {n[3:6]}-{n[6:8]}-{n[8:]}',
        'компаний': len(r['инн']),
        'фио': sorted(r['фио'])[:3],
        'источники': sorted(r['источники'])[:3],
        'пример_ссылки': (r['пример_url'] or '')[:80],
    } for n, r in shared[:12]]

    # то же по ФИО
    by_person = {}
    for inn, person in cx.execute(
            "select inn, person from phone_contacts where coalesce(person,'')<>''"):
        by_person.setdefault(person.strip(), set()).add(inn)
    many = sorted(((p, s) for p, s in by_person.items() if len(s) > 1),
                  key=lambda x: -len(x[1]))
    out['фио_на_многих_ИНН'] = [{'фио': p, 'компаний': len(s)} for p, s in many[:12]]
    print(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()
