# -*- coding: utf-8 -*-
r"""Ответы-сироты: письмо пришло, а к получателю не привязалось.

Лента диалога берёт входящие строго по recipient_id (store.dialog_thread:
WHERE recipient_id=?). Событие без него не попадёт НИКУДА — ни в карточку
лида, ни в переписку компании, — хотя письмо забрано и лежит в базе. Владелец
это и увидел: «здесь точно знаю что был ещё один ответ».
"""
import json
import re
import sqlite3

БД = r'C:\sender\sender.db'
АДРЕС = re.compile(r'[\w.+-]+@[\w.-]+\.\w+')

c = sqlite3.connect('file:%s?mode=ro' % БД.replace('\\', '/'), uri=True)
c.row_factory = sqlite3.Row
итог = {}
итог['всего_входящих'] = c.execute(
    "select count(*) from events where event_type in "
    "('reply','reply_auto','complaint','dsn','bounce')").fetchone()[0]
итог['без_получателя'] = c.execute(
    "select count(*) from events where event_type in "
    "('reply','reply_auto','complaint','dsn','bounce') "
    'and recipient_id is null').fetchone()[0]
итог['без_получателя_по_типам'] = dict(c.execute(
    "select event_type, count(*) from events where recipient_id is null "
    "and event_type in ('reply','reply_auto','complaint','dsn','bounce') "
    'group by event_type').fetchall())

# можно ли их привязать: адрес отправителя есть в recipients?
сироты = c.execute(
    "select id, event_ts, event_type, mailbox_id, detail_json from events "
    "where recipient_id is null and event_type in "
    "('reply','reply_auto','complaint','dsn','bounce') "
    'order by event_ts desc limit 400').fetchall()
чинимо, нечинимо, примеры = 0, 0, []
for r in сироты:
    try:
        d = json.loads(r['detail_json'] or '{}')
    except Exception:  # noqa: BLE001
        d = {}
    frm = (d.get('headers') or {}).get('From', '') or d.get('from') or ''
    m = АДРЕС.search(frm)
    адрес = (m.group(0).lower() if m else '')
    наш = None
    if адрес:
        наш = c.execute('select id, inn from recipients where lower(email)=?',
                        (адрес,)).fetchone()
    if наш:
        чинимо += 1
        if len(примеры) < 8:
            примеры.append({'событие': r['id'], 'когда': r['event_ts'],
                            'от': адрес, 'получатель': наш['id'],
                            'инн': наш['inn']})
    else:
        нечинимо += 1
        if len(примеры) < 12 and адрес:
            примеры.append({'событие': r['id'], 'когда': r['event_ts'],
                            'от': адрес, 'получатель': 'НЕ НАЙДЕН'})
итог['осмотрено_сирот'] = len(сироты)
итог['привяжутся_по_адресу'] = чинимо
итог['адрес_не_в_базе'] = нечинимо
итог['примеры'] = примеры
c.close()
print(json.dumps(итог, ensure_ascii=False, indent=1))
