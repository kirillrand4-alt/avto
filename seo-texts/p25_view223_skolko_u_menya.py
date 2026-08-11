# -*- coding: utf-8 -*-
"""Проверка чужого утверждения СВОИМ прибором. 1-я сессия (запись 131) говорит:
ссылка `epz/organization/view223/info.html?...inn=...` доказывает ИНН, но признак «ИНН есть
на странице» ЛОЖНЫЙ — страница печатает ИНН из собственного адреса даже для выдуманного.
Различает три условия сразу: ИНН после слова + ОГРН + «Местонахождение».

Считаю, сколько таких ссылок у МЕНЯ и сколько моих фактов держатся ТОЛЬКО на них."""
import collections, csv, io, os, re
OPS = r'C:\sender\_ops'
BAZA = os.path.join(OPS, 'PARK-BAZA-EDINAYA-3S.csv')
VIEW223 = re.compile(r'organization/view223', re.I)
sch = collections.Counter()
tolko = []
primery = []
with io.open(BAZA, encoding='utf-8-sig') as f:
    for r in csv.DictReader(f, delimiter=';'):
        us = [u for u in str(r.get('istochniki') or '').split(' | ') if u.startswith('http')]
        if not us:
            continue
        sch['строк со ссылками'] += 1
        v = [u for u in us if VIEW223.search(u)]
        if not v:
            continue
        sch['строк, где есть ссылка view223'] += 1
        sch['ссылок view223 всего'] += len(v)
        if len(v) == len(us):
            sch['строк, где view223 — ЕДИНСТВЕННАЯ ссылка'] += 1
            tolko.append((r.get('inn'), (r.get('predpriyatie') or '')[:40], v[0]))
        if len(primery) < 6:
            primery.append(v[0])
print('########## ЧИСЛА')
for k, val in sch.most_common():
    print('  %-46s %6d' % (k, val))
print('  --- строки, держащиеся ТОЛЬКО на view223 (до 8)')
for i, p, u in tolko[:8]:
    print('    %-12s %-40s %s' % (i, p, u[:90]))
print('  --- примеры адресов для перепроверки браузером')
for u in primery:
    print('    ' + u)
