# -*- coding: utf-8 -*-
"""Где сегодняшний ответ клиенту: очередь, письма, события, карточка лида."""
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
s.row_factory = sqlite3.Row
итог = {}
итог['очередь_ответов'] = [{k: (str(r[k])[:70] if r[k] is not None else None)
                            for k in ('id', 'kind', 'status', 'email', 'subject',
                                      'decided_by', 'decided_at', 'thread_id',
                                      'in_reply_to')}
                           for r in s.execute(
    "select * from confirm_reviews where kind='reply' order by id desc limit 6")]
итог['письма_ответы'] = [{k: (str(r[k])[:70] if r[k] is not None else None)
                          for k in ('id', 'status', 'subject', 'sent_at',
                                    'in_reply_to', 'thread_id', 'recipient_id')}
                         for r in s.execute(
    "select * from messages where coalesce(in_reply_to,'')<>'' "
    'order by id desc limit 6')]
итог['события_лидов'] = [dict(r) for r in s.execute(
    "select lead_id, action, from_status, to_status, substr(coalesce(detail_json,''),1,90) d, "
    'created_at from lead_events order by id desc limit 10')]
итог['лиды_не_new'] = [dict(r) for r in s.execute(
    "select id, coalesce(company_name,'') nm, status, coalesce(assigned_to,'') кому, "
    "coalesce(reply_kind,'') kind from leads where status<>'new' limit 8")]
итог['статусы_лидов'] = [list(r) for r in s.execute(
    'select status, count(*) from leads group by 1')]
s.close()
print(json.dumps(итог, ensure_ascii=False, indent=1, default=str)[:4200])
