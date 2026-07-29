# -*- coding: utf-8 -*-
"""Откат ошибочной привязки вакансий hh к АО «Криогенмаш».

Запасной путь взял из выдачи первую ссылку hh.ru/employer/<id> и попал на
«Завод Химического и Криогенного машиностроения» (Екатеринбург) — другую
компанию с похожим названием. Шесть телефонов кадровиков и два человека были
записаны под ИНН 5001000066 неверно. Удаляем ровно их, по источнику и ссылке,
предварительно записав удаляемое в журнал.
"""
import io
import json
import os
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

ИНН = '5001000066'
ЖУРНАЛ = r'C:\seostat\drop\hh_misattributed.jsonl'
e = EDB.EnrichDB().cx


def main():
    тел = [dict(zip(('rowid', 'phone', 'person', 'role', 'source', 'source_url'), r))
           for r in e.execute(
        "select rowid, phone, person, role, source, source_url from phone_contacts "
        "where inn=? and source like 'hh%'", (ИНН,))]
    люди = [dict(zip(('rowid', 'person', 'post', 'source', 'source_url'), r))
            for r in e.execute(
        "select rowid, person, post, source, source_url from people "
        "where inn=? and source like 'hh%'", (ИНН,))]
    with io.open(ЖУРНАЛ, 'a', encoding='utf-8') as f:
        for x in тел + люди:
            f.write(json.dumps({'инн': ИНН, 'причина': 'чужой работодатель на hh',
                                'запись': x}, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())
    e.executemany('delete from phone_contacts where rowid=?',
                  [(x['rowid'],) for x in тел])
    e.executemany('delete from people where rowid=?',
                  [(x['rowid'],) for x in люди])
    e.commit()
    print(json.dumps({'удалено_телефонов': len(тел), 'удалено_людей': len(люди),
                      'журнал': ЖУРНАЛ,
                      'осталось_телефонов_у_инн': e.execute(
                          'select count(*) from phone_contacts where inn=?',
                          (ИНН,)).fetchone()[0],
                      'осталось_людей_у_инн': e.execute(
                          'select count(*) from people where inn=?',
                          (ИНН,)).fetchone()[0]}, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
