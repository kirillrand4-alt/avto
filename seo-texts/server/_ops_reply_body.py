# -*- coding: utf-8 -*-
"""Где лежит ПОЛНЫЙ текст входящего ответа клиента (и лежит ли вообще)."""
import json
import sqlite3

DB = r'C:\sender\sender.db'


def main():
    cx = sqlite3.connect(f'file:{DB}?mode=ro', uri=True, timeout=30)
    cx.row_factory = sqlite3.Row
    out = {}

    out['события_reply'] = []
    for r in cx.execute("select id,event_type,event_ts,dedup_key,detail_json "
                        "from events where event_type in ('reply','other') "
                        "order by id desc limit 12"):
        d = r['detail_json'] or ''
        out['события_reply'].append({
            'id': r['id'], 'тип': r['event_type'], 'ключ': r['dedup_key'],
            'длина_detail': len(d), 'detail': d[:400]})

    out['leads_need'] = [
        {'id': r['id'], 'email': r['email'], 'длина_need': len(str(r['need'] or '')),
         'need_целиком': str(r['need'] or '')}
        for r in cx.execute('select * from leads')]

    # есть ли вообще где-то полный текст входящего
    tabs = [r[0] for r in cx.execute(
        "select name from sqlite_master where type='table'")]
    out['все_таблицы'] = tabs
    print(json.dumps(out, ensure_ascii=False, default=str))


if __name__ == '__main__':
    main()
