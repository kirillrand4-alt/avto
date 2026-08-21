# -*- coding: utf-8 -*-
r"""Откуда в базе роли: сколько их и у чего именно.

Вопрос владельца 21.08 — «откуда мы берём роли в принципе». Кодом отвечать
мало: важно, сколько ролей реально проставлено и у каких сущностей.
"""
import json
import sqlite3

c = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=60)
c.row_factory = sqlite3.Row
d = {}


def _счёт(sql, *п):
    try:
        return c.execute(sql, п).fetchone()[0]
    except Exception as e:  # noqa: BLE001
        return 'ошибка: ' + str(e)[:60]


d['почты'] = {
    'всего': _счёт('select count(*) from emails'),
    'с_ролью': _счёт("select count(*) from emails where coalesce(role,'')<>''"),
    'с_ролью_кроме_общей': _счёт(
        "select count(*) from emails where coalesce(role,'') not in "
        "('','общий','общий/приёмная')"),
    'с_именем_человека': _счёт("select count(*) from emails "
                               "where coalesce(person,'')<>''"),
}
d['роли_почт'] = {r[0]: r[1] for r in c.execute(
    "select coalesce(role,'(пусто)') r, count(*) n from emails "
    'group by r order by n desc limit 14')}
d['люди'] = {
    'всего': _счёт('select count(*) from people'),
    'с_должностью': _счёт("select count(*) from people where coalesce(post,'')<>''"),
    'с_ролью': _счёт("select count(*) from people where coalesce(role,'')<>''"),
    'компаний': _счёт('select count(distinct inn) from people'),
}
d['должности_людей'] = {r[0]: r[1] for r in c.execute(
    "select coalesce(role,'(пусто)') r, count(*) n from people "
    'group by r order by n desc limit 12')}
d['телефоны'] = {
    'строк_в_phone_contacts': _счёт('select count(*) from phone_contacts'),
    'с_ролью': _счёт("select count(*) from phone_contacts "
                     "where coalesce(role,'') not in ('','общий')"),
    'с_человеком': _счёт("select count(*) from phone_contacts "
                         "where coalesce(person,'')<>''"),
    'компаний_с_номером_в_таблице': _счёт(
        'select count(distinct inn) from phone_contacts'),
    'компаний_с_номером_в_companies': _счёт(
        "select count(*) from companies where coalesce(phones,'') not in ('','[]')"),
}
d['источники_почт'] = {r[0]: r[1] for r in c.execute(
    "select coalesce(source,'(пусто)') s, count(*) n from emails "
    'group by s order by n desc limit 10')}
c.close()
print(json.dumps(d, ensure_ascii=False, indent=1))
