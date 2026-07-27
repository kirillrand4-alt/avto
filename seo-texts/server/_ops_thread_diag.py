# -*- coding: utf-8 -*-
"""Разбор ленты лида: обрезка тела и достоверность склейки в ОДНУ ветку."""
import json
import sqlite3

DB = r'C:\sender\sender.db'
INN = '2124009521'


def main():
    cx = sqlite3.connect(f'file:{DB}?mode=ro', uri=True, timeout=30)
    cx.row_factory = sqlite3.Row
    out = {}

    rec = cx.execute('select id,email,inn,company_name from recipients where inn=?',
                     (INN,)).fetchall()
    out['получатели'] = [dict(r) for r in rec]
    rids = [r['id'] for r in rec]

    if rids:
        q = ','.join('?' for _ in rids)
        out['письма'] = [
            {'id': r['id'], 'кому': r['recipient_id'], 'статус': r['status'],
             'тема': r['subject'], 'rfc': r['rfc_message_id'],
             'in_reply_to': r['in_reply_to'] if 'in_reply_to' in r.keys() else None,
             'длина_тела': len(r['body_rendered'] or ''),
             'хвост_тела': (r['body_rendered'] or '')[-70:]}
            for r in cx.execute(
                f'select * from messages where recipient_id in ({q}) order by id', rids)]

        out['лиды'] = [
            {'id': r['id'], 'статус': r['status'],
             'длина_need': len(str(r['need'] or '')) if 'need' in r.keys() else None,
             'хвост_need': (str(r['need'] or ''))[-70:] if 'need' in r.keys() else None}
            for r in cx.execute(
                f'select * from leads where recipient_id in ({q})', rids)]

        out['confirm_reviews'] = [
            {'id': r['id'], 'kind': r['kind'], 'статус': r['status'],
             'тема': r['subject'], 'thread_id': r['thread_id'],
             'in_reply_to': r['in_reply_to'],
             'message_id': r['message_id'],
             'длина_body': len(r['body'] or ''),
             'длина_edited': len(r['edited_body'] or ''),
             'хвост': ((r['edited_body'] or r['body'] or ''))[-70:]}
            for r in cx.execute(
                f'select * from confirm_reviews where recipient_id in ({q}) order by id',
                rids)]

    # входящие: где лежит текст ответа клиента
    tabs = [r[0] for r in cx.execute(
        "select name from sqlite_master where type='table'")]
    out['таблицы_с_входящими'] = [t for t in tabs if any(
        k in t.lower() for k in ('inbound', 'incoming', 'reply', 'imap', 'lead'))]
    for t in out['таблицы_с_входящими']:
        cols = [c[1] for c in cx.execute(f'PRAGMA table_info({t})')]
        out[f'колонки_{t}'] = cols
    print(json.dumps(out, ensure_ascii=False, default=str))


if __name__ == '__main__':
    main()
