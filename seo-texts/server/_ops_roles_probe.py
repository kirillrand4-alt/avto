# -*- coding: utf-8 -*-
"""Что дал прогон ролей: роли телефонов и разные ли у них страницы-источники."""
import json
import sqlite3

ENR = r'C:\sender\enrich.db'


def main():
    cx = sqlite3.connect(f'file:{ENR}?mode=ro', uri=True, timeout=60)
    cx.row_factory = sqlite3.Row
    out = {}
    out['роли_телефонов'] = [{'роль': r[0], 'шт': r[1]} for r in cx.execute(
        "select role, count(*) from phone_contacts where source='сайт:обход' "
        'group by role order by 2 desc limit 25')]
    out['свежие'] = [dict(r) for r in cx.execute(
        "select inn, phone, person, role, source_url from phone_contacts "
        "where source='сайт:обход' order by updated_at desc limit 14")]
    # главный признак «кликабельная страница по номеру»: у компании должны быть
    # РАЗНЫЕ ссылки у разных номеров, а не одна на всех
    out['ссылок_на_компанию'] = [
        {'инн': r[0], 'телефонов': r[1], 'разных_ссылок': r[2]} for r in cx.execute(
            "select inn, count(*), count(distinct source_url) from phone_contacts "
            "where source='сайт:обход' group by inn order by 2 desc limit 10")]
    print(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()
