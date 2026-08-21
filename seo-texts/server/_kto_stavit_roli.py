# -*- coding: utf-8 -*-
r"""Кто на самом деле проставил роли: разрез по источнику записи.

Владелец 21.08 спросил прямо — «роли определяет не провайдер?». Ответ должен
быть не по памяти, а по базе: смотрим, у каких источников роль есть, а у каких
её нет, и сколько компаний вообще прошло через провайдерское извлечение.
"""
import json
import sqlite3

c = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=60)
c.row_factory = sqlite3.Row
d = {}


def разрез(таблица, поле_роли='role'):
    строки = {}
    for r in c.execute(
            "select coalesce(source,'(пусто)') s, "
            "sum(case when coalesce(%s,'') not in ('','общий') then 1 else 0 end) с_ролью, "
            'count(*) всего from %s group by s order by всего desc limit 12'
            % (поле_роли, таблица)):
        строки[r['s'][:26]] = {'всего': r['всего'], 'с_ролью': r['с_ролью'],
                               'доля_%': round(100.0 * r['с_ролью'] /
                                               max(1, r['всего']), 1)}
    return строки


ТЕЛ = разрез('phone_contacts')
ПОЧТ = разрез('emails')
# сколько компаний прошло провайдерское извлечение контактов
try:
    d['stage_log'] = {r[0]: r[1] for r in c.execute(
        'select stage, count(distinct inn) n from stage_log '
        'group by stage order by n desc limit 12')}
except Exception as e:  # noqa: BLE001
    d['stage_log'] = str(e)[:80]
d['телефоны_с_отделом'] = c.execute(
    "select count(*) from phone_contacts where coalesce(role,'') not in ('','общий')"
).fetchone()[0]
d['роль_снята_как_общий_номер'] = c.execute(
    "select count(*) from phone_contacts where coalesce(source,'') like '%общий номер%'"
).fetchone()[0]
c.close()
print(json.dumps({'ПОЧТЫ': ПОЧТ}, ensure_ascii=False, indent=1)[:1800])
print(json.dumps({'ТЕЛЕФОНЫ': ТЕЛ}, ensure_ascii=False, indent=1)[:1800])
print(json.dumps(d, ensure_ascii=False, indent=1)[:900])
