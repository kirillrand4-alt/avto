# -*- coding: utf-8 -*-
r"""Откуда взять имена НАШИХ отправителей, чтобы прятать их на странице лида."""
import json
import re

d = {}
with open(r'C:\sender\sender.yaml', encoding='utf-8') as f:
    текст = f.read()
d['from_name_в_yaml'] = re.findall(r'from_name\s*:\s*(.+)', текст)[:30]
d['имена_ящиков'] = re.findall(r'^\s*-?\s*name\s*:\s*(.+)$', текст, re.M)[:20]
# как выглядит строка атрибуции цитаты в живых ответах
import sqlite3
s = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True, timeout=60)
s.row_factory = sqlite3.Row
кол = [x[1] for x in s.execute('PRAGMA table_info(messages)')]
d['колонки_messages'] = кол
поле = 'body' if 'body' in кол else next(
    (k for k in ('text', 'body_text', 'content') if k in кол), '')
if поле:
    ряды = s.execute(
        'select %s t from messages where %s like ? limit 3' % (поле, поле),
        ('%Кому:%',)).fetchall()
    d['примеры_атрибуции'] = []
    for r in ряды:
        for стр in str(r['t'] or '').splitlines():
            if re.search(r'^\s*(-{4,}|Кому\s*:|Тема\s*:|\d{2}\.\d{2}\.\d{4})', стр):
                d['примеры_атрибуции'].append(стр.strip()[:120])
s.close()
print(json.dumps(d, ensure_ascii=False, indent=1)[:2600])
