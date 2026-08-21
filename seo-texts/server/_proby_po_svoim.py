# -*- coding: utf-8 -*-
r"""689 адресов на СВОЁМ домене: что о них уже знает проба.

Если адрес info@zavod.ru с домена самого zavod.ru уже прошёл пробу, вопрос
«снят он с сайта или из Checko» перестаёт быть важным: ящик существует и
принимает почту. Смотрим, сколько таких уже проверено и с каким исходом.
"""
import json
import re
import sqlite3
import sys

sys.path.insert(0, r'C:\sender\server')
import dogruz_935 as D  # noqa: E402


def домен(u):
    u = re.sub(r'^https?://', '', str(u or '').strip().lower()).strip('/')
    u = u.split('/')[0].split('?')[0]
    return u[4:] if u.startswith('www.') else u


def ядро(d):
    ч = [x for x in d.split('.') if x]
    if len(ч) > 2 and ч[-2] in ('com', 'org', 'net', 'co'):
        return '.'.join(ч[-3:])
    return '.'.join(ч[-2:]) if len(ч) >= 2 else d


c = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=60)
c.row_factory = sqlite3.Row
цель = {str(r[0]) for r in c.execute(
    "select inn from site_facts where coalesce(format,0)>=2 "
    "and facts_json like '%\"продукция\": [\"%'")}
цель -= {str(r[0]) for r in c.execute(
    'select distinct e.inn from emails e where %s and %s' % (D.САЙТ, D.ЧИСТ))}
сайты = {str(r[0]): ядро(домен(r[1] or r[2] or '')) for r in c.execute(
    "select inn, coalesce(site,''), coalesce(cand_site,'') from companies")}
свои = {}
for r in c.execute("select inn, lower(email) em, coalesce(source,'') src from emails"):
    и = str(r['inn'])
    if и not in цель:
        continue
    if сайты.get(и) and ядро(домен(r['em'].split('@')[-1])) == сайты[и]:
        свои.setdefault(и, []).append(r['em'])
адреса = {a for сп in свои.values() for a in сп}
d = {'компаний_свой_домен': len(свои), 'адресов': len(адреса)}
таблицы = [x[0] for x in c.execute(
    "select name from sqlite_master where type='table' and ("
    "name like '%probe%' or name like '%proba%' or name like '%smtp%')")]
d['таблицы_пробы'] = таблицы
for т in таблицы:
    колонки = [x[1] for x in c.execute('PRAGMA table_info(%s)' % т)]
    if 'email' not in [k.lower() for k in колонки]:
        continue
    поле = [k for k in колонки if k.lower() == 'email'][0]
    исход = [k for k in колонки if k.lower() in
             ('verdict', 'verdikt', 'status', 'result', 'itog', 'rezultat')]
    сч = {}
    for r in c.execute('select lower(%s) em, %s v from %s'
                       % (поле, исход[0] if исход else "''", т)):
        if r[0] in адреса:
            сч[str(r[1])[:24]] = сч.get(str(r[1])[:24], 0) + 1
    d['проба_%s' % т] = {'колонки': колонки[:8],
                         'по_нашим_адресам': dict(sorted(сч.items(),
                                                         key=lambda x: -x[1])[:8])}
c.close()
print(json.dumps(d, ensure_ascii=False, indent=1))
