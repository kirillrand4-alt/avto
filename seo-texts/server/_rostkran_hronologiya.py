# -*- coding: utf-8 -*-
"""Вся переписка с «Росткраном» по времени: кто писал, что, когда."""
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
s.row_factory = sqlite3.Row
ПОЧТА = 'chernyavin@rostkran.ru'
итог = {}
л = s.execute("select id, company_name, inn, status, reply_kind, created_at, "
              "coalesce(need,'') need from leads where lower(email)=?",
              (ПОЧТА,)).fetchone()
итог['лид'] = {k: (str(л[k])[:200] if л[k] is not None else None)
               for k in л.keys()} if л else 'нет'
итог['очередь'] = [{'id': r['id'], 'вид': r['kind'], 'статус': r['status'],
                    'тема': (r['subject'] or '')[:60],
                    'создано': r['created_at'], 'решено': r['decided_at'],
                    'кем': (r['decided_by'] or '')[:30],
                    'текст': (r['edited_body'] or r['body'] or '')[:150]}
                   for r in s.execute(
    "select * from confirm_reviews where lower(coalesce(email,''))=? "
    'order by id', (ПОЧТА,))]
итог['отправки'] = [dict(r) for r in s.execute(
    "select ts, coalesce(subject,'') тема, coalesce(outcome,'') исход "
    'from send_log where lower(coalesce(email,\'\'))=? order by ts', (ПОЧТА,))]
итог['события'] = [dict(r) for r in s.execute(
    "select event_type, event_ts from events where recipient_id in "
    "(select id from recipients where lower(coalesce(email,''))=?) "
    'order by event_ts', (ПОЧТА,))]
s.close()
print(json.dumps(итог, ensure_ascii=False, indent=1, default=str)[:3800])
