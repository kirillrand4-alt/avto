# -*- coding: utf-8 -*-
"""Обернуть ошибку в прибавку: 341 человек с НАЗВАННЫМ работодателем — есть ли он в нашей базе.

Ложная привязка снята, но люди настоящие: имя, должность и предприятие названы в источнике.
Если чьё-то из 294 упомянутых предприятий есть у нас, человека надо привязать ТУДА — и тогда
находка владельца обернётся приростом, а не только исправлением.

Сверка по СЛОВАМ имени, а не по строке: «Нижнекамскшина» в цитате против
«АО "НИЖНЕКАМСКШИНА"» в базе — одно предприятие. Порог: совпало хотя бы одно отличительное
слово длиной от шести букв, и оно не из отраслевого словаря.
"""
import collections
import csv
import json
import re
import sqlite3

OBSHEE = set("""завод комбинат фабрика объединение управление предприятие филиал общество
акционерное ограниченной ответственностью компания холдинг корпорация группа станция
водоканал теплосеть энерго нефть газ химия""".split())


def slova(s):
    return {w.lower() for w in re.split(r'[^А-Яа-яЁёA-Za-z0-9]+', s or '')
            if len(w) >= 6 and w.lower() not in OBSHEE}


cx = sqlite3.connect(r'C:\seostat\data\centrifugal.db')
baza = []
for inn, naz in cx.execute("select inn, coalesce(predpriyatie,'') from company"):
    baza.append((inn, naz, slova(naz)))

rows = list(csv.DictReader(open(r'C:\sender\_ops\3s_VAZHNOE-3s-CHUZHAYA-PRIVYAZKA-449.csv',
                               encoding='utf-8-sig'), delimiter=';'))
nashli, ne_nashli = [], collections.Counter()
for r in rows:
    ego = (r.get('ego_predpriyatie') or '').strip()
    s = slova(ego)
    if not s:
        ne_nashli['название без отличительных слов'] += 1
        continue
    kand = [(inn, naz) for inn, naz, sb in baza if s & sb]
    if len(kand) == 1:
        nashli.append({'fio': r['fio'], 'dolzhnost': r['dolzhnost'],
                       'ego_predpriyatie': ego, 'nayden_inn': kand[0][0],
                       'nayden_nazvanie': kand[0][1][:70], 'byl_privyazan_k': r['nash_inn'],
                       'citata': r['citata'][:200]})
    elif len(kand) > 1:
        ne_nashli['несколько кандидатов — не привязываю вслепую'] += 1
    else:
        ne_nashli['предприятия нет в нашей базе'] += 1
print(json.dumps({'строк': len(rows), 'НАЙДЕНО в базе однозначно': len(nashli),
                  'разных людей': len({(x['fio'], x['nayden_inn']) for x in nashli}),
                  'не найдено': dict(ne_nashli),
                  'примеры': nashli[:6]}, ensure_ascii=False, indent=1)[:2500])
