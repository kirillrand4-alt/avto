# -*- coding: utf-8 -*-
r"""Привязать уже пришедшие ответы-сироты к получателям.

Починка на приёме (imap_watcher + store.poluchatel_dlya_vhodyashchego) работает
с нового письма. Те, что уже лежат в базе с recipient_id=NULL, надо привязать
разово — иначе живые ответы клиентов так и останутся невидимыми в ленте.

    python pochinka_sirot.py            посмотреть, кого привяжет
    python pochinka_sirot.py --primenit привязать
"""
import json
import os
import re
import sqlite3
import sys
import time

БД = os.environ.get('SENDER_DB', r'C:\sender\sender.db')
АДРЕС = re.compile(r'[\w.+-]+@[\w.-]+\.\w+')
ТИПЫ = ('reply', 'reply_auto', 'complaint', 'dsn', 'bounce')
# Ящиков на бесплатной почте в базе тысячи, поэтому «единственный получатель с
# этим доменом, которому мы писали» — совпадение, а не признак той же компании.
ФРИМЕЙЛ = {'mail.ru', 'inbox.ru', 'bk.ru', 'list.ru', 'internet.ru', 'yandex.ru',
           'ya.ru', 'gmail.com', 'rambler.ru', 'icloud.com', 'outlook.com',
           'hotmail.com', 'yahoo.com', 'mail.com', 'narod.ru', 'pochta.ru'}


def адрес_из(detail):
    frm = ((detail.get('headers') or {}).get('From', '')
           or detail.get('from') or '')
    m = АДРЕС.search(str(frm))
    return m.group(0).lower() if m else ''


def главное(применять=False):
    c = sqlite3.connect(БД, timeout=60)
    c.row_factory = sqlite3.Row
    сироты = c.execute(
        'select id, event_ts, event_type, detail_json from events '
        'where recipient_id is null and event_type in (%s) '
        'order by event_ts' % ','.join('?' * len(ТИПЫ)), ТИПЫ).fetchall()
    свод = {'сирот': len(сироты), 'по_references': 0, 'по_адресу': 0,
            'по_домену': 0, 'не_привязано': 0}
    правки, разбор = [], []
    for r in сироты:
        try:
            d = json.loads(r['detail_json'] or '{}')
        except Exception:  # noqa: BLE001
            d = {}
        адрес = адрес_из(d)
        if not адрес:
            свод['не_привязано'] += 1
            continue
        # 1) вся цепочка References: там лежит НАШ Message-ID, даже если
        # In-Reply-To указывает на пересылку. Так опознаётся ответ коллеги,
        # которому переслали наше письмо.
        h = d.get('headers') or {}
        как, найден = '', None
        сырьё = '%s %s' % (h.get('References', '') or '', h.get('In-Reply-To', '') or '')
        for m in re.finditer(r'<[^<>\s]+>', сырьё):
            стр = c.execute(
                'select r.id, r.inn from messages m join recipients r '
                'on r.id=m.recipient_id where m.rfc_message_id=? limit 1',
                (m.group(0),)).fetchone()
            if стр:
                найден, как = стр, 'references'
                break
        if not найден:
            найден = c.execute(
                'select id, inn from recipients where lower(email)=?', (адрес,)).fetchone()
            if найден:
                как = 'адрес'
        if not найден:
            # ответ с другого адреса того же домена, куда мы писали
            домен = адрес.split('@')[-1]
            if домен in ФРИМЕЙЛ:
                домен = ''            # см. ФРИМЕЙЛ: случайность, а не связь
            ряды = [] if not домен else c.execute(
                'select r.id, r.inn from recipients r where r.domain=? '
                'and exists(select 1 from messages m where m.recipient_id=r.id '
                'and m.sent_at is not null) order by r.id limit 2', (домен,)).fetchall()
            if len(ряды) == 1:
                найден, как = ряды[0], 'домен'
        if not найден:
            свод['не_привязано'] += 1
            разбор.append({'событие': r['id'], 'от': адрес, 'итог': 'не нашли компанию'})
            continue
        свод['по_' + ('references' if как == 'references'
                      else 'адресу' if как == 'адрес' else 'домену')] += 1
        правки.append((найден['id'], r['id']))
        разбор.append({'событие': r['id'], 'когда': r['event_ts'], 'от': адрес,
                       'получатель': найден['id'], 'инн': найден['inn'], 'как': как})
    if применять and правки:
        c.execute('PRAGMA busy_timeout=30000')
        for попытка in range(6):
            try:
                c.executemany('update events set recipient_id=? where id=?', правки)
                c.commit()
                свод['привязано'] = len(правки)
                break
            except sqlite3.OperationalError as e:
                if 'locked' not in str(e) and 'busy' not in str(e):
                    raise
                time.sleep(2 * (попытка + 1))
    c.close()
    свод['разбор'] = разбор[:20]
    свод['ts'] = time.strftime('%Y-%m-%dT%H:%M:%S')
    print(json.dumps(свод, ensure_ascii=False, indent=1))
    print(json.dumps({'итог': {k: v for k, v in свод.items() if k != 'разбор'}},
                     ensure_ascii=False))


if __name__ == '__main__':
    главное('--primenit' in sys.argv)
