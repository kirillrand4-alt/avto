# -*- coding: utf-8 -*-
"""Откуда берутся телефоны: схема phone_contacts, источники, роли, ссылки.

Нужно, чтобы понять, какой код заполняет таблицу (в репозитории писателя нет)
и где именно ставить роль телефона. Ничего не пишет — только читает.
"""
import json
import sqlite3

ENR = r'C:\sender\enrich.db'
SALES = r'C:\sender\_ops\sales_base.json'


def main():
    cx = sqlite3.connect(f'file:{ENR}?mode=ro', uri=True, timeout=60)
    cx.row_factory = sqlite3.Row
    out = {}
    out['схема'] = [dict(имя=r[1], тип=r[2]) for r in
                    cx.execute('pragma table_info(phone_contacts)')]
    out['всего'] = cx.execute('select count(*) from phone_contacts').fetchone()[0]
    out['источники'] = [{'источник': r[0] or '?', 'шт': r[1], 'с_ролью': r[2],
                         'с_ФИО': r[3], 'со_ссылкой': r[4]}
                        for r in cx.execute(
        "select source, count(*), "
        "sum(case when coalesce(trim(role),'')<>'' then 1 else 0 end), "
        "sum(case when coalesce(trim(person),'')<>'' then 1 else 0 end), "
        "sum(case when coalesce(trim(source_url),'')<>'' then 1 else 0 end) "
        'from phone_contacts group by source order by 2 desc limit 20')]
    out['роли_телефонов'] = [{'роль': r[0], 'шт': r[1]} for r in cx.execute(
        "select role, count(*) from phone_contacts "
        "where coalesce(trim(role),'')<>'' group by role order by 2 desc limit 20")]
    out['образцы'] = [dict(r) for r in cx.execute(
        'select inn, phone, person, role, source, source_url '
        'from phone_contacts order by rowid desc limit 6')]

    # то же по базе продажников (555) — цель прогона
    try:
        inns = [str(c.get('inn')) for c in json.load(open(SALES, encoding='utf-8'))
                if c.get('inn')]
    except Exception:  # noqa: BLE001
        inns = []
    if inns:
        q = ','.join('?' for _ in inns)
        out['база_продажников'] = {
            'ИНН': len(set(inns)),
            'телефонов': cx.execute(
                f'select count(*) from phone_contacts where inn in ({q})',
                inns).fetchone()[0],
            'с_ролью': cx.execute(
                f"select count(*) from phone_contacts where inn in ({q}) "
                "and coalesce(trim(role),'')<>''", inns).fetchone()[0],
            'со_ссылкой': cx.execute(
                f"select count(*) from phone_contacts where inn in ({q}) "
                "and coalesce(trim(source_url),'')<>''", inns).fetchone()[0],
            'компаний_с_сайтом': cx.execute(
                f"select count(*) from companies where inn in ({q}) "
                "and coalesce(trim(site),'')<>''", inns).fetchone()[0],
        }
    print(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()
