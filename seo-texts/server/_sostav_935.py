# -*- coding: utf-8 -*-
r"""Состав группы после широкой заливки: фримейл, домены, свежие строки."""
import json
import sqlite3

ФРИ = ('mail.ru', 'yandex.ru', 'ya.ru', 'gmail.com', 'bk.ru', 'inbox.ru',
       'list.ru', 'rambler.ru', 'internet.ru', 'icloud.com', 'mail.com',
       'yandex.com', 'outlook.com', 'hotmail.com')
c = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True, timeout=60)
c.row_factory = sqlite3.Row
всего = фри = 0
свежие = свежие_фри = 0
домены = {}
for r in c.execute("select lower(coalesce(email,'')) em, coalesce(extra_json,'') ex, "
                   "coalesce(created_at,'') cr from recipients "
                   "where extra_json like '%Партия 935%'"):
    if not r['em']:
        continue
    всего += 1
    д = r['em'].split('@')[-1]
    домены[д] = домены.get(д, 0) + 1
    ф = д in ФРИ
    if ф:
        фри += 1
    if r['cr'][:10] >= '2026-08-24':
        свежие += 1
        if ф:
            свежие_фри += 1
c.close()
print(json.dumps({
    'в_группе_адресов': всего,
    'фримейл_всего': фри,
    'доля_фримейла_проц': round(100.0 * фри / max(1, всего), 1),
    'заведено_сегодня': свежие,
    'из_них_фримейл': свежие_фри,
    'доля_среди_новых_проц': round(100.0 * свежие_фри / max(1, свежие), 1),
    'частые_домены': dict(sorted(домены.items(), key=lambda x: -x[1])[:10]),
}, ensure_ascii=False, indent=1))
