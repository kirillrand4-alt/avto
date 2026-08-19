# -*- coding: utf-8 -*-
"""Отделить ЗАГЛУШКИ (test/example/demo) от обычных общих ящиков (info/mail)."""
import json
import re
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
ЗАГЛУШКА = re.compile(r'^(test|tests|testing|proba|primer|example|sample|demo|'
                      r'noreply|no-reply|donotreply|nobody|user|qwerty|asdf|'
                      r'admin|root|webmaster|postmaster)@', re.I)
ОБЩИЙ = re.compile(r'^(info|mail|email|office|zakaz|sales|shop|1|123)@', re.I)
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
s.row_factory = sqlite3.Row
заглушки, общие = [], 0
for r in s.execute("select lower(coalesce(email,'')) em, coalesce(inn,'') inn "
                   "from confirm_reviews where status='approved'"):
    a = r['em']
    if ЗАГЛУШКА.match(a or ''):
        заглушки.append({'адрес': a, 'инн': r['inn'], 'имя': ''})
    elif ОБЩИЙ.match(a or ''):
        общие += 1
итог = {'заглушек_в_подтверждённых': len(заглушки),
        'обычных_общих_ящиков': общие, 'заглушки': заглушки[:20]}
# и по всей базе получателей — сколько таких заглушек вообще
всего = 0
for (a,) in s.execute("select lower(coalesce(email,'')) from recipients"):
    if ЗАГЛУШКА.match(a or ''):
        всего += 1
итог['заглушек_среди_всех_получателей'] = всего
s.close()
print(json.dumps(итог, ensure_ascii=False, indent=1))
