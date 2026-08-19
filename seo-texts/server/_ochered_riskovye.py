# -*- coding: utf-8 -*-
"""Что стоит в подтверждённой очереди автоотправки с сомнительными адресами.

Смотрим ЖДУЩИЕ отправки (approved, но ещё не sent) и ставим каждому адресу
метку риска: вердикт пробы «неясно»/нет вердикта/«принимает всё», а также
явно служебные и подозрительные адреса (test@, noreply@, example@ и т.п.).
"""
import json
import re
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
ПОДОЗРИТЕЛЬНЫЕ = re.compile(
    r'^(test|tests|testing|proba|primer|example|sample|demo|noreply|no-reply|'
    r'donotreply|nobody|user|admin|root|webmaster|postmaster|abuse|spam|'
    r'mail|email|info|1|123|qwerty|asdf)@', re.I)
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
s.row_factory = sqlite3.Row
верд = {str(r[0]).lower(): r[1] for r in s.execute('select email, verdict from addr_probe')}
стоп = {str(r[0]).lower() for r in s.execute(
    "select value from suppression where scope='email'")}
итог = {'по_статусам_очереди': [dict(r) for r in s.execute(
    'select status, count(*) n from confirm_reviews group by 1 order by n desc')]}
ждут = [dict(r) for r in s.execute(
    "select id, lower(coalesce(email,'')) em, coalesce(inn,'') inn, "
    "coalesce(campaign_id,0) camp, coalesce(decided_by,'') кем, "
    "coalesce(decided_at,'') когда, coalesce(subject,'') тема "
    "from confirm_reviews where status='approved'")]
итог['подтверждено_ждёт_отправки'] = len(ждут)
риски, примеры = {}, {}
for r in ждут:
    a = r['em']
    метки = []
    if not a or '@' not in a:
        метки.append('адреса нет вовсе')
    else:
        в = верд.get(a)
        if a in стоп:
            метки.append('адрес в стоп-листе')
        if в is None:
            метки.append('проба не проверяла')
        elif в == 'неясно':
            метки.append('вердикт «неясно»')
        elif в in ('нет ящика', 'нет MX'):
            метки.append('вердикт «мёртв»')
        elif в == 'принимает всё':
            метки.append('домен принимает всё')
        if ПОДОЗРИТЕЛЬНЫЕ.match(a):
            метки.append('служебный/тестовый вид адреса')
    for м in метки or ['чисто']:
        риски[м] = риски.get(м, 0) + 1
        сп = примеры.setdefault(м, [])
        if len(сп) < 5:
            сп.append({'адрес': a, 'инн': r['inn'], 'кем': r['кем'][:40],
                       'когда': r['когда'][:16]})
итог['риски'] = dict(sorted(риски.items(), key=lambda kv: -kv[1]))
итог['примеры'] = примеры
s.close()
print(json.dumps(итог, ensure_ascii=False, indent=1, default=str)[:4600])
