# -*- coding: utf-8 -*-
"""Что за 496 «прочих» в догрузе: почему их не было в партии при заливке."""
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
САЙТ = "(e.source in ('own-site','zenno') or e.source like 'сайт:%')"
ЧИСТ = ("coalesce(e.pometka,'') not like '%спам-ловушк%' "
        "and coalesce(e.pometka,'') not like '%скрыт%' "
        "and coalesce(e.pometka,'') not like '%не использовать%'")
c = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/enrich.db', uri=True)
c.row_factory = sqlite3.Row
годные, сайтовые = {}, {}
for r in c.execute(
        "select k.inn, coalesce(nullif(k.short_name,''),k.name,'') name, "
        "coalesce(k.best_email,'') best, coalesce(k.updated_at,'') upd "
        'from companies k where exists(select 1 from emails e where e.inn=k.inn '
        'and %s and %s) and exists(select 1 from site_facts f where f.inn=k.inn '
        'and coalesce(f.format,0)>=2 and f.facts_json like \'%%"продукция": ["%%\')'
        % (САЙТ, ЧИСТ)):
    годные[str(r['inn'])] = dict(r)
for r in c.execute('select e.inn, lower(e.email) em from emails e where %s and %s'
                   % (САЙТ, ЧИСТ)):
    сайтовые.setdefault(str(r['inn']), set()).add(r['em'])
ts = {str(r[0]): (r[1] or '') for r in c.execute(
    "select inn, ts from site_facts where coalesce(facts_json,'')<>''")}
c.close()
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
в_группе, все_адреса, чей = set(), set(), {}
for инн, em, ex in s.execute("select coalesce(inn,''), lower(coalesce(email,'')), "
                             "coalesce(extra_json,'') from recipients"):
    и = ''.join(ch for ch in инн if ch.isdigit())
    if em:
        все_адреса.add(em)
        чей[em] = и
    if 'Партия 935' in ex:
        в_группе.add(и)
s.close()

прочие, причины = [], {}
for i, v in годные.items():
    if i in в_группе:
        continue
    if ts.get(i, '') >= '2026-08-17T12':
        continue
    b = (v['best'] or '').lower()
    if b and чей.get(b, i) != i:
        continue
    сп = сайтовые.get(i) or set()
    if not b:
        п = 'best_email пуст — писать не на что'
    elif b not in сп:
        п = 'best_email НЕ сайтовый (из обзвона), а сайтовые адреса есть'
    elif b in все_адреса:
        п = 'адрес уже в панели за этой же компанией, но вне группы'
    else:
        п = 'должен был попасть — проверить отдельно'
    причины[п] = причины.get(п, 0) + 1
    if len(прочие) < 5 and п.startswith('должен'):
        прочие.append({'инн': i, 'имя': v['name'][:35], 'почта': b})
print(json.dumps({'причины': причины, 'примеры_странных': прочие},
                 ensure_ascii=False, indent=1))
