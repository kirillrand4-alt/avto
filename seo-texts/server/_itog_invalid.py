# -*- coding: utf-8 -*-
"""Починен ли «invalid mailbox»: что в партии сейчас и что осталось дырой."""
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
ГРУППА = 'Партия 935'
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
s.row_factory = sqlite3.Row
верд = {str(r[0]).lower(): r[1] for r in s.execute('select email, verdict from addr_probe')}
стоп = {str(r[0]).lower() for r in s.execute(
    "select value from suppression where scope='email'")}
в_группе, счёт, мёртвые_в_группе = 0, {}, []
без_вердикта = 0
for em, ex, инн in s.execute("select lower(coalesce(email,'')), coalesce(extra_json,''), "
                             "coalesce(inn,'') from recipients"):
    if not em:
        continue
    try:
        d = json.loads(ex) if ex.strip() else {}
    except Exception:  # noqa: BLE001
        continue
    if ГРУППА not in [str(g) for g in (d.get('gruppy') or [])]:
        continue
    в_группе += 1
    в = верд.get(em, '(нет вердикта)')
    счёт[в] = счёт.get(в, 0) + 1
    if в in ('нет ящика', 'нет MX'):
        мёртвые_в_группе.append({'инн': инн, 'адрес': em, 'вердикт': в,
                                 'в_стопе': em in стоп})
    if в == '(нет вердикта)':
        без_вердикта += 1
итог = {'в_группе': в_группе, 'по_вердиктам': dict(sorted(счёт.items(), key=lambda kv: -kv[1])),
        'мёртвых_осталось_в_группе': len(мёртвые_в_группе),
        'примеры_мёртвых': мёртвые_в_группе[:5]}
# отбивки после того, как мы начали проверять заранее
итог['отбивки_по_часам_сегодня'] = [dict(r) for r in s.execute(
    "select substr(event_ts,1,13) h, count(*) n from events "
    "where event_type='bounce' and event_ts >= '2026-08-19' group by 1 order by 1")]
итог['всего_проверено_адресов'] = len(верд)
итог['в_стоп-листе_по_адресу'] = len(стоп)
s.close()
print(json.dumps(итог, ensure_ascii=False, indent=1))
