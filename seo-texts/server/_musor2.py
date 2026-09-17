# -*- coding: utf-8 -*-
"""Только явные признаки бесполезности: нет компании или нет действия — по тексту разбора."""
import json, sqlite3

ПРИЗНАКИ = (
    'заказчик в тексте не назван', 'конкретный заказчик не', 'заказчик не назван',
    'компания не названа', 'название компании отсутствует', 'компания-инвестор не',
    'текст обрезан', 'текст новости обрезан', 'подробности обрезаны',
    'конкретное действие не указано', 'конкретика отсутствует',
    'детали о проекте, этапе или инвестициях в тексте отсутствуют',
    'детали не указаны', 'информация не раскрывается', 'контекст не уточнён',
)
c = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True, timeout=40)
всего = c.execute('select count(*) from signals').fetchone()[0]
строки = c.execute(
    "select s.rowid, s.inn, coalesce(cmp.name,''), s.event_type, s.what, s.source, s.source_url "
    'from signals s left join companies cmp on cmp.inn=s.inn').fetchall()
c.close()
мусор, примеры = [], []
for rid, inn, имя, тип, what, src, url in строки:
    t = (what or '').lower()
    if any(p in t for p in ПРИЗНАКИ):
        мусор.append((rid, inn, url))
        if len(примеры) < 7:
            примеры.append({'компания': (имя or inn)[:32], 'тип': тип,
                            'что': (what or '')[:120], 'источник': src})
print('===ИТОГ===')
print(json.dumps({'сигналов_всего': всего, 'мусора_по_признакам': len(мусор),
                  'доля_%': round(100.0*len(мусор)/max(всего,1), 1),
                  'примеры': примеры}, ensure_ascii=False, indent=1)[:3600])
