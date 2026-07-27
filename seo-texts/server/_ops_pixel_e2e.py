# -*- coding: utf-8 -*-
"""Сквозная проверка пикселя: токен -> публичный URL -> событие open в БД.

Берём ТЕСТОВОЕ письмо (кампания addrtest), чтобы не создавать ложное открытие
в боевой статистике.
"""
import json
import sqlite3
import sys
import time
import urllib.request

sys.path.insert(0, r'C:\sender')

DB = r'C:\sender\sender.db'
TEST_MID = 445          # [ADDRTEST-...] проверка смены адреса, кампания 3


def main():
    out = {}
    from sender.config import Config
    from sender.store import Store
    from sender.tracking import OpenTracker

    cfg = Config.load(r'C:\sender\sender.yaml')
    store = Store(cfg.get('service.db_path', 'sender.db'))
    tr = OpenTracker(cfg, store)

    cx = sqlite3.connect(f'file:{DB}?mode=ro', uri=True, timeout=30)
    row = cx.execute('select id,recipient_id,campaign_id,sent_at from messages '
                     'where id=?', (TEST_MID,)).fetchone()
    if not row:
        print(json.dumps({'итог': f'нет письма {TEST_MID}'}, ensure_ascii=False))
        return
    out['письмо'] = {'id': row[0], 'recipient': row[1], 'campaign': row[2],
                     'sent_at': row[3]}
    before = cx.execute("select count(*) from events where event_type='open'").fetchone()[0]
    out['open_до'] = before
    cx.close()

    token = tr.make_token(row[0], row[1], row[2])
    url = tr.pixel_url(token)
    out['url_пикселя'] = url[:60] + '...'
    out['база_url'] = url.split('/o/')[0]

    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            out['ответ'] = {'код': r.status, 'тип': r.headers.get('Content-Type'),
                            'байт': len(r.read())}
    except Exception as e:  # noqa: BLE001
        out['ответ'] = str(e)[:200]

    time.sleep(3)
    cx = sqlite3.connect(f'file:{DB}?mode=ro', uri=True, timeout=30)
    after = cx.execute("select count(*) from events where event_type='open'").fetchone()[0]
    out['open_после'] = after
    ev = cx.execute("select event_type,event_ts,dedup_key from events "
                    "where event_type='open' order by event_ts desc limit 3").fetchall()
    out['события'] = [{'тип': e[0], 'время': e[1], 'ключ': e[2]} for e in ev]
    cx.close()
    out['итог'] = 'ПИКСЕЛЬ РАБОТАЕТ' if after > before else 'событие не записалось'
    print(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()
