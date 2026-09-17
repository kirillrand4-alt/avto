# -*- coding: utf-8 -*-
"""Сколько в signals строк, бесполезных по содержанию (без компании и без действия)."""
import json, re, sqlite3

c = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True, timeout=40)
всего = c.execute('select count(*) from signals').fetchone()[0]
строки = c.execute(
    "select s.rowid, s.inn, coalesce(cmp.name,''), s.event_type, s.what, s.source "
    'from signals s left join companies cmp on cmp.inn=s.inn').fetchall()
c.close()

ПРИЗНАКИ = (
    'заказчик в тексте не назван', 'конкретный заказчик не', 'компания не названа',
    'текст обрезан', 'текст новости обрезан', 'конкретное действие не указано',
    'подробности обрезаны', 'детали не указаны', 'конкретика отсутствует',
    'информация не раскрывается', 'название компании отсутствует',
    'конкретные детали о проекте', 'детали о проекте, этапе или инвестициях в тексте отсутствуют',
)
мусор, примеры = [], []
for rid, inn, имя, тип, what, src in строки:
    t = (what or '').lower()
    if any(p in t for p in ПРИЗНАКИ) or len((what or '').strip()) < 40:
        мусор.append((rid, inn, src))
        if len(примеры) < 8:
            примеры.append({'компания': имя[:35] or inn, 'тип': тип,
                            'что': (what or '')[:110], 'источник': src})
print('===ИТОГ===')
print(json.dumps({'сигналов_всего': всего, 'подходит_под_критерий': len(мусор),
                  'доля_%': round(100.0*len(мусор)/max(всего,1), 1),
                  'примеры': примеры}, ensure_ascii=False, indent=1)[:3800])
