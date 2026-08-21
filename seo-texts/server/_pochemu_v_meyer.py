# -*- coding: utf-8 -*-
r"""Почему компрессорное письмо #3585 видно в очереди Meyer.

Проверяем ровно ту развилку, что стоит в app.confirm_queue: направление ПИСЬМА
(panel.letter_division, иначе лексика текста), а если его нет — метку компании.
Предикат пропускает письмо в обе очереди, когда направление неизвестно.
"""
import json
import os
import sqlite3
import sys

sys.path.insert(0, r'C:\sender')
sys.path.insert(0, r'C:\sender\sender')

МАРКЕРЫ = {
    'kc': ('компрессор', 'азот', 'кислород', ' мкс', 'пневмо', 'воздуходув'),
    'meyer': ('рентген', 'фотосепар', 'фото-сепар', 'инспекц', 'сортировк'),
}
d = {}
s = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True, timeout=60)
s.row_factory = sqlite3.Row
таблицы = [r[0] for r in s.execute(
    "select name from sqlite_master where type='table'")]
d['таблицы_похожие'] = [t for t in таблицы
                        if 'review' in t or 'confirm' in t or 'queue' in t]
таб = 'reviews' if 'reviews' in таблицы else (
    d['таблицы_похожие'][0] if d['таблицы_похожие'] else '')
d['таблица'] = таб
if таб:
    d['колонки'] = [x[1] for x in s.execute('PRAGMA table_info(%s)' % таб)]
    ряд = s.execute('select * from %s where id=?' % таб, (3585,)).fetchone()
    if ряд:
        r = dict(ряд)
        panel = {}
        for ключ in ('panel', 'panel_json', 'extra_json'):
            if r.get(ключ):
                try:
                    panel = json.loads(r[ключ]) or {}
                    break
                except Exception:  # noqa: BLE001
                    pass
        d['письмо'] = {
            'id': r.get('id'), 'статус': r.get('status'),
            'тема': str(r.get('subject') or '')[:80],
            'letter_division_в_panel': (panel.get('letter_division')
                                        if isinstance(panel, dict) else None),
            'ключи_panel': sorted(panel.keys())[:14] if isinstance(panel, dict) else [],
            'company_division': (((panel.get('company') or {}).get('division'))
                                 if isinstance(panel, dict) else None),
        }
        текст = ' '.join([str(r.get('subject') or ''), str(r.get('body') or ''),
                          json.dumps(panel, ensure_ascii=False)]).lower()
        попало = {k for k, ms in МАРКЕРЫ.items() if any(m in текст for m in ms)}
        d['лексика'] = {
            'попало': sorted(попало),
            'kc_маркеры': [m for m in МАРКЕРЫ['kc'] if m in текст],
            'meyer_маркеры': [m for m in МАРКЕРЫ['meyer'] if m in текст],
            'вывод_letter_division': (list(попало)[0] if len(попало) == 1 else None),
        }
        напр = 'meyer'
        реш = d['лексика']['вывод_letter_division'] or (
            d['письмо']['company_division'] or '')
        d['предикат'] = {'напр': напр, 'd': реш,
                         'показывать': (not реш) or (напр in str(реш).lower())}
    else:
        d['письмо'] = 'ряда 3585 нет'
s.close()
print(json.dumps(d, ensure_ascii=False, indent=1)[:4000])
