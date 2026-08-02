# -*- coding: utf-8 -*-
"""Замер: у скольких из 1486 целей без техЛПР вообще известен сайт.

Обход подразделений отработал 57 целей из 1486 — это 3.8%. Для промышленных
предприятий такая доля означает не «сайтов нет», а «сайт не записан». Прежде
чем искать новые каналы, надо померить, где именно обрыв: в базе, в
кандидатах или действительно в природе.
"""
import csv
import io
import json
import os
import sys

sys.path.insert(0, r'C:\sender\server')
sys.path.insert(0, r'C:\seostat')
import enrich_db as EDB  # noqa: E402

ДРОП = r'C:\seostat\drop\drop-storage'


def main():
    csv.field_size_limit(10 ** 7)
    п = os.path.join(ДРОП, 'BEZ-TEHLPR-1486.csv')
    инны = []
    if os.path.exists(п):
        for r in csv.DictReader(io.StringIO(
                open(п, encoding='utf-8-sig', errors='replace').read()),
                delimiter=';'):
            и = (r.get('inn') or '').strip()
            if и:
                инны.append(и)
    инны = list(dict.fromkeys(инны))

    db = EDB.EnrichDB()
    cx = db.cx
    кол = {r[1] for r in cx.execute('PRAGMA table_info(companies)')}
    итог = {'целей': len(инны), 'колонки_companies': sorted(кол)}

    есть_сайт = канд = нет_строки = пусто = 0
    примеры = []
    for и in инны:
        поля = ['site'] + (['cand_site'] if 'cand_site' in кол else [])
        q = cx.execute(
            'SELECT %s FROM companies WHERE inn=?' % ','.join(поля), (и,)
        ).fetchone()
        if not q:
            нет_строки += 1
            continue
        с = (q[0] or '').strip()
        к = (q[1] or '').strip() if len(q) > 1 else ''
        if с:
            есть_сайт += 1
            if len(примеры) < 5:
                примеры.append({'inn': и, 'site': с})
        elif к:
            канд += 1
        else:
            пусто += 1
    итог.update({'сайт_подтверждён': есть_сайт, 'только_кандидат': канд,
                 'пусто': пусто, 'нет_строки_в_companies': нет_строки,
                 'примеры': примеры})

    # сколько у них вообще есть телефонов/почт/людей — чтобы понять, что
    # именно тянуть дальше
    def скольким(запрос):
        n = 0
        for и in инны:
            if cx.execute(запрос, (и,)).fetchone()[0]:
                n += 1
        return n

    итог['с_телефоном'] = скольким(
        'SELECT COUNT(*) FROM phone_contacts WHERE inn=?')
    итог['с_почтой'] = скольким('SELECT COUNT(*) FROM emails WHERE inn=?')
    итог['с_людьми'] = скольким('SELECT COUNT(*) FROM people WHERE inn=?')
    print(json.dumps(итог, ensure_ascii=False))


if __name__ == '__main__':
    main()
