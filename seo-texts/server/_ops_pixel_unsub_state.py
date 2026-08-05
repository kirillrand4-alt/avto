# -*- coding: utf-8 -*-
"""Что сейчас реально уходит в письме: пиксель, ссылки, заголовки отписки.

Читаем боевой конфиг (секции tracking/legal) и последние отправленные письма из
боевой БД — включая конкретное письмо на el5-energo.ru, по которому пришла
отбивка «500 Message rejected». Только чтение, секреты не печатаем.
"""
import glob
import json
import os
import re
import sqlite3

OUT = {}


def _cfg_section(raw, name):
    m = re.search(r'^%s:\s*$(.*?)^(?=\S)' % name, raw, re.M | re.S)
    return (m.group(1).rstrip() if m else '(нет секции)')


def main():
    # 1) конфиги
    for path in (r'C:\sender\config.yaml', r'C:\sender\sender.yaml'):
        if not os.path.exists(path):
            continue
        raw = open(path, encoding='utf-8', errors='replace').read()
        OUT[os.path.basename(path)] = {
            'tracking': _cfg_section(raw, 'tracking'),
            'legal': _cfg_section(raw, 'legal'),
            'db_строки': [ln.strip() for ln in raw.splitlines()
                          if re.search(r'\b(db|database|store)\b.*:', ln)][:6],
        }

    # 2) БД
    cands = [r'C:\sender\sender.db', r'C:\sender\data\sender.db']
    cands += glob.glob(r'C:\sender\*.db') + glob.glob(r'C:\sender\data\*.db')
    db = next((p for p in cands if os.path.exists(p)), None)
    OUT['db'] = db
    if not db:
        print(json.dumps(OUT, ensure_ascii=False))
        return
    con = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
    con.row_factory = sqlite3.Row

    def q(sql, args=()):
        try:
            return [dict(r) for r in con.execute(sql, args).fetchall()]
        except Exception as e:  # noqa: BLE001
            return [{'error': str(e)}]

    OUT['всего_sent'] = q("SELECT COUNT(*) c FROM messages WHERE status='sent'")
    # письмо, по которому отбивка
    rows = q("""SELECT m.id, m.sent_at, m.status, m.subject, m.rfc_message_id,
                       LENGTH(m.body_rendered) blen, m.body_rendered, r.email
                  FROM messages m JOIN recipients r ON r.id=m.recipient_id
                 WHERE r.email LIKE '%el5-energo%' OR m.body_rendered LIKE '%el5-energo%'
                 ORDER BY m.id DESC LIMIT 5""")
    OUT['письма_el5'] = []
    for r in rows:
        body = r.pop('body_rendered', '') or ''
        r['ссылки_в_теле'] = sorted(set(re.findall(r'https?://[^\s<>"\)]+', body)))
        r['есть_html_тег'] = bool(re.search(r'<\w+', body))
        r['хвост_тела'] = body[-400:]
        OUT['письма_el5'].append(r)
    # последние письма вообще — те же признаки
    rows = q("""SELECT m.id, m.sent_at, r.email, m.body_rendered
                  FROM messages m JOIN recipients r ON r.id=m.recipient_id
                 WHERE m.status='sent' ORDER BY m.id DESC LIMIT 8""")
    OUT['последние_письма'] = [{
        'id': r['id'], 'sent_at': r['sent_at'], 'email': r['email'],
        'ссылки': sorted(set(re.findall(r'https?://[^\s<>"\)]+', r['body_rendered'] or '')))
    } for r in rows if 'error' not in r]
    OUT['события_bounce'] = q(
        "SELECT type, COUNT(*) c FROM events GROUP BY type ORDER BY c DESC LIMIT 12")
    OUT['панель_настройки'] = q(
        "SELECT key, substr(value,1,60) v FROM panel_settings "
        "WHERE key LIKE '%track%' OR key LIKE '%unsub%' OR key LIKE '%pixel%'")
    print(json.dumps(OUT, ensure_ascii=False))


if __name__ == '__main__':
    main()
