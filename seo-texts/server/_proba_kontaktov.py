# -*- coding: utf-8 -*-
"""Что вернёт новый блок контактов для «Росткрана» и пары других лидов."""
import json
import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
путь = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')


def контакты(инн):
    цифры = ''.join(c for c in str(инн or '') if c.isdigit())
    cx = sqlite3.connect('file:%s?mode=ro' % путь, uri=True)
    cx.row_factory = sqlite3.Row
    люди = [dict(r) for r in cx.execute(
        "SELECT person, COALESCE(post,'') post, COALESCE(role,'') role, "
        "COALESCE(phone,'') phone, COALESCE(email,'') email, "
        "COALESCE(source,'') source, COALESCE(source_url,'') source_url "
        "FROM people WHERE inn=? AND COALESCE(person,'')<>''", (цифры,))]
    тел = [dict(r) for r in cx.execute(
        "SELECT phone, COALESCE(role,'') role, COALESCE(source_url,'') source_url "
        'FROM phone_contacts WHERE inn=?', (цифры,))]
    почты = [dict(r) for r in cx.execute(
        "SELECT email, COALESCE(role,'') role, COALESCE(source_url,'') source_url "
        'FROM emails WHERE inn=?', (цифры,))]
    cx.close()
    return {'людей': len(люди), 'телефонов': len(тел), 'почт': len(почты),
            'люди': люди[:3], 'телефоны': тел[:3], 'почты': почты[:3]}


s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
лиды = [dict(zip(('id', 'nm', 'inn'), r)) for r in s.execute(
    "select id, coalesce(company_name,''), coalesce(inn,'') from leads "
    "where coalesce(inn,'')<>'' order by id desc limit 4")]
s.close()
print(json.dumps([{'лид': l['id'], 'компания': l['nm'][:24],
                   **контакты(l['inn'])} for l in лиды],
                 ensure_ascii=False, indent=1)[:3000])
