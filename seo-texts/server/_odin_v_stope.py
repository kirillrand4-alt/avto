# -*- coding: utf-8 -*-
"""Подтверждённые письма на адресах из стоп-листа: кто и за что."""
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
s.row_factory = sqlite3.Row
стоп = {str(r[0]).lower(): (r[1], r[2]) for r in s.execute(
    "select value, coalesce(reason,''), coalesce(source,'') from suppression "
    "where scope='email'")}
стоп_инн = {''.join(c for c in str(r[0]) if c.isdigit()): (r[1] or '')
            for r in s.execute("select value, reason from suppression where scope='inn'")}
из = []
for r in s.execute("select id, lower(coalesce(email,'')) em, coalesce(inn,'') inn, "
                   "coalesce(subject,'') t, status from confirm_reviews "
                   "where status in ('approved','pending')"):
    инн = ''.join(c for c in r['inn'] if c.isdigit())
    if r['em'] in стоп:
        из.append({'адрес': r['em'], 'статус': r['status'], 'почему': стоп[r['em']][0],
                   'источник': стоп[r['em']][1][:60], 'тема': r['t'][:40], 'вид': 'адрес'})
    elif инн and инн in стоп_инн:
        из.append({'адрес': r['em'], 'статус': r['status'], 'инн': инн,
                   'почему': стоп_инн[инн], 'тема': r['t'][:40], 'вид': 'ИНН'})
s.close()
свод = {}
for x in из:
    свод['%s:%s' % (x['вид'], x['почему'])] = свод.get('%s:%s' % (x['вид'], x['почему']), 0) + 1
print(json.dumps({'всего': len(из), 'свод': свод, 'строки': из[:12]},
                 ensure_ascii=False, indent=1))
