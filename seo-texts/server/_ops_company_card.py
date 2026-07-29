# -*- coding: utf-8 -*-
"""Всё, что база знает о компании: поиск по названию или ИНН.

Запуск: python _ops_company_card.py "криогенмаш"  |  python ... 5001000064
"""
import json
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

e = EDB.EnrichDB().cx


def строки(sql, args=()):
    cur = e.execute(sql, args)
    поля = [d[0] for d in cur.description]
    return [dict(zip(поля, r)) for r in cur.fetchall()]


def другие_базы(ключ):
    """Компания может лежать не в enrich.db, а в базах обзвона и в списках,
    с которых всё начиналось. Ищем везде, иначе «не найдено» соврёт."""
    import glob
    import os
    import sqlite3
    из = []
    к = ключ.lower()
    # Базы обзвона лежат НЕ рядом с enrich.db: centrifugal.db и seo.db в
    # C:\seostat\data, индекс обзвона в C:\sender. Без этих путей поиск
    # честно возвращал «не найдено» там, где компания есть.
    пути = (glob.glob(r'C:\sender\*.db') + glob.glob(r'C:\sender\**\*.db')
            + glob.glob(r'C:\seostat\drop\*.db')
            + glob.glob(r'C:\seostat\data\*.db')
            + glob.glob(r'C:\seostat\**\*.db'))
    for путь in sorted(set(пути)):
        if путь.lower().endswith('enrich.db'):
            continue
        try:
            cx = sqlite3.connect(f'file:{путь}?mode=ro', uri=True, timeout=10)
            табл = [r[0] for r in cx.execute(
                "select name from sqlite_master where type='table'")]
            for t in табл:
                поля = [r[1] for r in cx.execute(f'pragma table_info({t})')]
                имена = [f for f in поля if f.lower() in
                         ('name', 'company', 'title', 'org', 'наименование',
                          'company_name', 'org_name', 'full_name', 'short_name')]
                if not имена:
                    continue
                усл = ' or '.join(f'lower({f}) like ?' for f in имена)
                try:
                    cur = cx.execute(f'select * from {t} where {усл} limit 3',
                                     [f'%{к}%'] * len(имена))
                    п = [d[0] for d in cur.description]
                    for r in cur.fetchall():
                        из.append({'база': os.path.basename(путь), 'таблица': t,
                                   'строка': {a: b for a, b in zip(п, r)
                                              if b not in (None, '')}})
                except Exception:  # noqa: BLE001
                    continue
            cx.close()
        except Exception:  # noqa: BLE001
            continue
    for ф in (r'C:\sender\_ops\sales_base.json',
              r'C:\sender\server\core396.json'):
        try:
            j = json.load(open(ф, encoding='utf-8'))
        except Exception:  # noqa: BLE001
            continue
        куски = j.values() if isinstance(j, dict) else [j]
        for группа in куски:
            for x in (группа if isinstance(группа, list) else []):
                if к in json.dumps(x, ensure_ascii=False).lower():
                    из.append({'файл': ф.rsplit(chr(92), 1)[-1], 'строка': x})
    return из[:12]


def main():
    ключ = ' '.join(sys.argv[1:]).strip() or 'криогенмаш'
    if ключ.isdigit():
        нашли = строки('select * from companies where inn=?', (ключ,))
    else:
        нашли = строки('select * from companies where lower(name) like ? '
                       'order by length(name) limit 6', (f'%{ключ.lower()}%',))
    out = {'запрос': ключ, 'найдено_компаний': len(нашли), 'карточки': []}
    for c in нашли[:4]:
        inn = c['inn']
        к = {'инн': inn, 'название': c.get('name'),
             'сайт': c.get('site') or c.get('cand_site'),
             'город': c.get('region'), 'оквэд': c.get('okved'),
             'подтверждение': c.get('verified'),
             'конкурент': c.get('is_competitor'),
             'деятельность': (c.get('activity') or '')[:200]}
        for поле in ('revenue_rub', 'division', 'pxr'):
            if поле in c:
                к[поле] = c[поле]
        к['люди'] = строки(
            'select person, post, role, phone, email, source, source_url '
            'from people where inn=? order by role', (inn,))
        к['телефоны'] = строки(
            'select phone, person, role, source, source_url '
            'from phone_contacts where inn=? order by role limit 40', (inn,))
        к['почты'] = строки(
            'select email, person, role, mx_ok, source, source_url '
            'from emails where inn=? order by role limit 40', (inn,))
        к['сигналы'] = строки(
            'select event_type, what, sum, hotness, source_url, ts '
            'from signals where inn=? order by hotness desc limit 12', (inn,))
        к['этапы'] = строки(
            'select stage, detail, ts from stage_log where inn=? limit 20',
            (inn,))
        out['карточки'].append(к)
    if not нашли:
        out['в_других_базах'] = другие_базы(ключ)
    print(json.dumps(out, ensure_ascii=False, indent=1)[:12000])


if __name__ == '__main__':
    main()
