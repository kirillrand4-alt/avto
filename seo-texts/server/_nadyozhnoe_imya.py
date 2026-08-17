# -*- coding: utf-8 -*-
"""Где лежит имя, которому можно верить, и чем оно отличается от ненадёжного."""
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
e = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/enrich.db', uri=True)
e.row_factory = sqlite3.Row
итог = {}
итог['люди_всего'] = e.execute('select count(*) from people').fetchone()[0]
итог['люди_с_должностью'] = e.execute(
    "select count(*) from people where coalesce(person,'')<>'' and coalesce(post,'')<>''"
).fetchone()[0]
итог['люди_с_доказательством'] = e.execute(
    "select count(*) from people where coalesce(person,'')<>'' and coalesce(post,'')<>'' "
    "and coalesce(source_url,'')<>''").fetchone()[0]
итог['компаний_с_такими_людьми'] = e.execute(
    "select count(distinct inn) from people where coalesce(person,'')<>'' "
    "and coalesce(post,'')<>'' and coalesce(source_url,'')<>''").fetchone()[0]
итог['адресов_с_именем'] = e.execute(
    "select count(*) from emails where coalesce(person,'')<>''").fetchone()[0]
итог['адресов_имя_совпало_с_адресом'] = e.execute(
    "select count(*) from emails where coalesce(person,'')<>'' and imya_ok=1").fetchone()[0]
итог['адресов_заход_фио'] = e.execute(
    "select count(*) from emails where coalesce(zahod_fio,'')<>''").fetchone()[0]
итог['примеры_надёжных'] = [dict(r) for r in e.execute(
    "select inn, person, post, coalesce(role,'') role, substr(source_url,1,55) otkuda "
    "from people where coalesce(person,'')<>'' and coalesce(post,'')<>'' "
    "and coalesce(source_url,'')<>'' limit 4")]
итог['примеры_имя_к_адресу'] = [dict(r) for r in e.execute(
    "select inn, email, person, coalesce(role,'') role from emails "
    'where imya_ok=1 limit 4')]
e.close()
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
итог['в_панели_contact_name'] = s.execute(
    "select count(*) from recipients where coalesce(contact_name,'')<>''").fetchone()[0]
итог['в_панели_всего'] = s.execute('select count(*) from recipients').fetchone()[0]
s.close()
print(json.dumps(итог, ensure_ascii=False, indent=1)[:3000])
