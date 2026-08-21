# -*- coding: utf-8 -*-
r"""Партия 935: распределение ролей + проверка подозрительного получателя.

o.tseyzer@kompressor-pro-expert.ru в списке получателей выглядит как НАШ
собственный адрес — если так, письмо уйдёт самим себе. Проверяем по тем же
доменам отправки, что знает страница лида.
"""
import json
import sqlite3
import sys

sys.path.insert(0, r'C:\sender')
sys.path.insert(0, r'C:\sender\sender')
try:
    from sender import lid_ssylka as LS
except Exception:  # noqa: BLE001
    import lid_ssylka as LS

ГРУППА = 'Партия 935'
s = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True, timeout=60)
s.row_factory = sqlite3.Row
наши = LS.nashi_domeny()
свои_в_группе = []
получатели = []
for r in s.execute("select id, coalesce(inn,'') inn, lower(coalesce(email,'')) em, "
                   "coalesce(extra_json,'') ex, '' st from recipients"):
    if ГРУППА not in r['ex'] or not r['em']:
        continue
    инн = ''.join(c for c in str(r['inn']) if c.isdigit())
    получатели.append((инн, r['em']))
    if r['em'].split('@')[-1] in наши:
        свои_в_группе.append({'id': r['id'], 'адрес': r['em'], 'инн': инн,
                              'статус': r['st']})
# и вообще по всей панели
все_свои = [dict(r) for r in s.execute(
    'select id, email, coalesce(inn,\'\') inn from recipients')]
s.close()
чужие_наши = [x for x in все_свои
              if str(x['email'] or '').split('@')[-1].lower() in наши]

e = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=60)
почты = {}
for инн, ем, роль in e.execute("select inn, lower(email), coalesce(role,'') from emails"):
    почты[(str(инн), ем)] = роль
e.close()
роли = {}
for инн, адрес in получатели:
    р = почты.get((инн, адрес))
    if р is None:
        continue
    роли[р or '(пусто)'] = роли.get(р or '(пусто)', 0) + 1
print(json.dumps({'наших_доменов': len(наши),
                  'НАШИ_АДРЕСА_В_ГРУППЕ': свои_в_группе,
                  'наши_адреса_во_всей_панели': чужие_наши[:8],
                  'их_всего': len(чужие_наши)}, ensure_ascii=False, indent=1)[:1600])
print(json.dumps({'роли_получателей_935': dict(
    sorted(роли.items(), key=lambda x: -x[1])[:14])}, ensure_ascii=False, indent=1))
