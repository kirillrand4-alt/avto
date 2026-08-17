# -*- coding: utf-8 -*-
"""Полная карточка баунса и общая картина отказов."""
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
s.row_factory = sqlite3.Row
итог = {}
итог['события_по_типам'] = [dict(r) for r in s.execute(
    "select event_type, count(*) skolko, max(event_ts) posledniy from events "
    "group by event_type order by skolko desc")]
итог['баунсы'] = []
for r in s.execute("select * from events where event_type='bounce' order by id desc limit 5"):
    d = {}
    try:
        d = json.loads(r['detail_json'] or '{}')
    except Exception:
        pass
    dsn = d.get('dsn') or {}
    пол = s.execute("select coalesce(email,'') email, coalesce(inn,'') inn, "
                    "coalesce(company_name,'') name, coalesce(role_based,'') rolevoy, coalesce(source,'') istochnik from recipients where id=?",
                    (r['recipient_id'],)).fetchone()
    отпр = s.execute("select coalesce(email,'') email, coalesce(subject,'') tema, "
                     "coalesce(ts,'') ts, coalesce(outcome,'') itog from send_log "
                     "where message_id=? or email=? order by id desc limit 1",
                     (r['message_id'], (пол['email'] if пол else ''))).fetchone()
    итог['баунсы'].append({
        'когда': r['event_ts'][:19], 'ящик_отправителя': r['mailbox_id'],
        'кампания': r['campaign_id'], 'провайдер': r['provider'],
        'кому': (dsn.get('failed') or [пол['email'] if пол else ''])[:1],
        'компания': (пол['name'][:45] if пол else ''), 'инн': (пол['inn'] if пол else ''),
        'адрес_ролевой': (пол['rolevoy'] if пол else ''),
        'откуда_адрес': (пол['istochnik'] if пол else ''),
        'ответ_сервера': dsn.get('diagnostic', ''), 'код': dsn.get('smtp_code'),
        'вердикт': dsn.get('verdict', ''),
        'письмо_ушло': (отпр['ts'][:19] if отпр else '—'),
        'тема': (отпр['tema'][:60] if отпр else '')})
итог['отправлено_всего'] = s.execute('select count(*) from send_log').fetchone()[0]
итог['по_итогам_отправки'] = [dict(r) for r in s.execute(
    "select coalesce(outcome,'') itog, count(*) skolko from send_log group by 1")]
s.close()
print(json.dumps(итог, ensure_ascii=False, indent=1)[:3000])
