# -*- coding: utf-8 -*-
r"""Партия 935: у скольких адресов рассылки роль определена, и кем.

Вопрос владельца 21.08 — «провайдер у почт у всех определял роли уже? из 935
партии». Считаем по тем адресам, которые реально стоят в панели как получатели
этой группы, а не по всей базе почт.
"""
import json
import sqlite3

ГРУППА = 'Партия 935'
s = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True, timeout=60)
получатели = []
for инн, адрес, ex in s.execute(
        "select coalesce(inn,''), lower(coalesce(email,'')), coalesce(extra_json,'') "
        'from recipients'):
    if ГРУППА in ex and адрес:
        получатели.append((''.join(c for c in str(инн) if c.isdigit()), адрес))
s.close()

e = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=60)
e.row_factory = sqlite3.Row
почты = {}
for r in e.execute("select inn, lower(email) em, coalesce(role,'') role, "
                   "coalesce(source,'') src, coalesce(person,'') person from emails"):
    почты[(str(r['inn']), r['em'])] = dict(r)
прошли = {str(r[0]) for r in e.execute(
    "select distinct inn from stage_log where stage='email'")}
e.close()

ст = {'получателей_в_группе': len(получатели), 'нашлось_в_обогащении': 0,
      'с_ролью': 0, 'роль_не_общая': 0, 'с_именем': 0, 'нет_в_обогащении': 0,
      'компания_прошла_извлечение': 0}
роли, источники, примеры = {}, {}, []
компании = set()
for инн, адрес in получатели:
    компании.add(инн)
    if инн in прошли:
        ст['компания_прошла_извлечение'] += 1
    р = почты.get((инн, адрес))
    if not р:
        ст['нет_в_обогащении'] += 1
        if len(примеры) < 5:
            примеры.append({'нет_в_обогащении': адрес, 'инн': инн})
        continue
    ст['нашлось_в_обогашении' if False else 'нашлось_в_обогащении'] += 1
    роль = (р['role'] or '').strip()
    роли[роль or '(пусто)'] = роли.get(роль or '(пусто)', 0) + 1
    источники[(р['src'] or '(пусто)')[:24]] = источники.get(
        (р['src'] or '(пусто)')[:24], 0) + 1
    if роль:
        ст['с_ролью'] += 1
    if роль and роль not in ('общий', 'приёмная', 'общий/приёмная'):
        ст['роль_не_общая'] += 1
    if (р['person'] or '').strip():
        ст['с_именем'] += 1
ст['компаний'] = len(компании)
print(json.dumps({'роли': dict(sorted(роли.items(), key=lambda x: -x[1])[:12]),
                  'источники_адресов': dict(sorted(источники.items(),
                                                   key=lambda x: -x[1])[:8])},
                 ensure_ascii=False, indent=1))
print(json.dumps({'счёт': ст, 'примеры': примеры}, ensure_ascii=False, indent=1))
