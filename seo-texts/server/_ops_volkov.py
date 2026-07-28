# -*- coding: utf-8 -*-
"""Кто такой «Волков И.» и почему он закупщик у многих компаний."""
import json
import sqlite3

DB = r'C:\sender\enrich.db'


def main():
    cx = sqlite3.connect(f'file:{DB}?mode=ro', uri=True, timeout=60)
    cx.row_factory = sqlite3.Row
    out = {}

    rows = cx.execute(
        "select p.inn, p.phone, p.person, p.role, p.source_url, c.name "
        "from phone_contacts p left join companies c on c.inn=p.inn "
        "where p.person like '%Волков%' order by p.inn").fetchall()
    out['телефоны_волкова'] = [
        {'инн': r['inn'], 'компания': (r['name'] or '')[:52],
         'тел': r['phone'], 'фио': r['person'],
         'карточка': (r['source_url'] or '')[-24:]} for r in rows]

    em = cx.execute(
        "select e.inn, e.email, e.person, e.source_url, c.name "
        "from emails e left join companies c on c.inn=e.inn "
        "where e.person like '%Волков%'").fetchall()
    out['почты_волкова'] = [
        {'инн': r['inn'], 'компания': (r['name'] or '')[:52],
         'email': r['email']} for r in em]

    # все ФИО, привязанные к тому же номеру
    out['на_этом_же_номере'] = [
        {'фио': r[0], 'компаний': r[1]} for r in cx.execute(
            "select person, count(distinct inn) from phone_contacts "
            "where replace(replace(replace(replace(phone,' ',''),'(',''),')',''),'-','') "
            "like '%4999494740%' group by person")]

    # чьи это ИНН: смотрим учредителей/названия
    inns = sorted({r['inn'] for r in rows})
    if inns:
        q = ','.join('?' for _ in inns)
        out['компании'] = [
            {'инн': r[0], 'название': (r[1] or '')[:70], 'сайт': r[2]}
            for r in cx.execute(
                f'select inn, name, site from companies where inn in ({q})', inns)]
    print(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()
