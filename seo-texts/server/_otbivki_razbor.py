# -*- coding: utf-8 -*-
"""Разбор отбивок: чей домен у адреса и по каким ящикам они бьют."""
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'C:\sender\server')
import ploshchadki as PL  # noqa: E402

s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
s.row_factory = sqlite3.Row
e = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/enrich.db', uri=True)

итог = {'по_ящикам_отправителя': [], 'адреса': []}
итог['по_ящикам_отправителя'] = [dict(r) for r in s.execute(
    "select mailbox_id, count(*) otbivok from events where event_type='bounce' "
    'group by mailbox_id order by otbivok desc limit 8')]
итог['всего_отправлено'] = s.execute("select count(*) from send_log").fetchone()[0]
итог['всего_отбивок'] = s.execute(
    "select count(*) from events where event_type='bounce'").fetchone()[0]

for r in s.execute("select recipient_id, event_ts, detail_json from events "
                   "where event_type='bounce' order by id desc limit 6"):
    пол = s.execute("select coalesce(email,'') email, coalesce(inn,'') inn, "
                    "coalesce(company_name,'') name, coalesce(domain,'') dom "
                    "from recipients where id=?", (r['recipient_id'],)).fetchone()
    if not пол:
        continue
    сайт = e.execute("select coalesce(site,cand_site,'') from companies where inn=?",
                     (пол['inn'],)).fetchone()
    дом_адреса = (пол['email'].split('@')[-1] or '').lower()
    дом_сайта = PL.домен(сайт[0]) if сайт and сайт[0] else ''
    итог['адреса'].append({
        'когда': r['event_ts'][:16], 'адрес': пол['email'],
        'компания': пол['name'][:40], 'инн': пол['inn'],
        'домен_адреса': дом_адреса, 'домен_сайта_компании': дом_сайта or '(сайта нет)',
        'совпадает': (дом_адреса == дом_сайта) if дом_сайта else None})
s.close(); e.close()
print(json.dumps(итог, ensure_ascii=False, indent=1)[:2600])
