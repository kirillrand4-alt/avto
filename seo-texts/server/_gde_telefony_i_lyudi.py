# -*- coding: utf-8 -*-
"""Где на самом деле лежат телефоны и люди: сравнение источников по всей базе."""
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
c = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/enrich.db', uri=True)
и = {}
и['компаний_всего'] = c.execute('select count(*) from companies').fetchone()[0]
и['с_телефонами_в_companies'] = c.execute(
    "select count(*) from companies where coalesce(phones,'') not in ('', '[]')"
).fetchone()[0]
и['с_телефонами_в_phone_contacts'] = c.execute(
    'select count(distinct inn) from phone_contacts').fetchone()[0]
и['есть_в_companies_но_нет_в_phone_contacts'] = c.execute(
    "select count(*) from companies k where coalesce(k.phones,'') not in ('', '[]') "
    'and not exists(select 1 from phone_contacts p where p.inn=k.inn)').fetchone()[0]
и['людей_в_people'] = c.execute(
    "select count(distinct inn) from people where coalesce(person,'')<>''").fetchone()[0]
и['людей_в_emails'] = c.execute(
    "select count(distinct inn) from emails where coalesce(person,'')<>''").fetchone()[0]
и['имя_в_emails_но_нет_в_people'] = c.execute(
    "select count(distinct e.inn) from emails e where coalesce(e.person,'')<>'' "
    "and not exists(select 1 from people p where p.inn=e.inn "
    "and coalesce(p.person,'')<>'')").fetchone()[0]
и['людей_с_должностью_в_emails'] = c.execute(
    "select count(*) from emails where coalesce(person,'')<>'' "
    "and coalesce(role,'') not in ('', 'общий')").fetchone()[0]
c.close()
print(json.dumps(и, ensure_ascii=False, indent=1))
