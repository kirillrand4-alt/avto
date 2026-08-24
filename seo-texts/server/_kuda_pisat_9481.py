# -*- coding: utf-8 -*-
r"""9481 паспортных компаний без «чистого адреса с сайта»: адреса-то у них есть?

Формулировка «писать некуда» была про наше правило отбора, а не про пустоту.
Считаем честно: есть ли у них почта хоть где-нибудь — в обогащении, в базе
обзвона, на своём домене — и что именно мешает такой адрес взять.
"""
import json
import re
import sqlite3

def домен(u):
    u = re.sub(r'^https?://', '', str(u or '').strip().lower()).strip('/')
    u = u.split('/')[0].split('?')[0]
    return u[4:] if u.startswith('www.') else u


def ядро(d):
    ч = [x for x in d.split('.') if x]
    if len(ч) > 2 and ч[-2] in ('com', 'org', 'net', 'co'):
        return '.'.join(ч[-3:])
    return '.'.join(ч[-2:]) if len(ч) >= 2 else d


e = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=60)
с_паспортом = {str(r[0]) for r in e.execute(
    "select inn from site_facts where coalesce(facts_json,'')<>'' "
    'and coalesce(format,0)>=2')}
чистый_с_сайта = {str(r[0]) for r in e.execute(
    "select distinct e.inn from emails e where (e.source in ('own-site','zenno') "
    "or e.source like 'сайт:%') and coalesce(e.pometka,'') not like '%спам-ловушк%' "
    "and coalesce(e.pometka,'') not like '%скрыт%' "
    "and coalesce(e.pometka,'') not like '%не использовать%'")}
цель = с_паспортом - чистый_с_сайта

сайты = {str(r[0]): ядро(домен(r[1] or r[2] or '')) for r in e.execute(
    "select inn, coalesce(site,''), coalesce(cand_site,'') from companies")}
почты, источники, пометки = {}, {}, {}
свой_домен = set()
for инн, ем, ист, пом in e.execute(
        "select inn, lower(email), coalesce(source,''), coalesce(pometka,'') "
        'from emails'):
    и = str(инн)
    if и not in цель:
        continue
    почты.setdefault(и, []).append(ем)
    источники[ист[:22] or '(пусто)'] = источники.get(ист[:22] or '(пусто)', 0) + 1
    if пом:
        пометки[пом[:34]] = пометки.get(пом[:34], 0) + 1
    if сайты.get(и) and ядро(домен(ем.split('@')[-1])) == сайты[и]:
        свой_домен.add(и)
# база обзвона
из_обзвона = set()
try:
    for r in e.execute("select inn from obzvon where coalesce(email,'')<>''"):
        и = str(r[0])
        if и in цель:
            из_обзвона.add(и)
except Exception as ex:  # noqa: BLE001
    из_обзвона = 'нет таблицы obzvon: %s' % str(ex)[:60]
e.close()

d = {'паспортных_без_чистого_адреса_с_сайта': len(цель),
     'из_них_адрес_есть_хоть_где_то': len(почты),
     'из_них_адреса_нет_нигде': len(цель) - len(почты),
     'адрес_на_ИХ_ЖЕ_домене': len(свой_домен),
     'есть_почта_в_базе_обзвона': (len(из_обзвона) if isinstance(из_обзвона, set)
                                   else из_обзвона),
     'источники_их_адресов': dict(sorted(источники.items(),
                                         key=lambda x: -x[1])[:10]),
     'пометки': dict(sorted(пометки.items(), key=lambda x: -x[1])[:6])}
print(json.dumps(d, ensure_ascii=False, indent=1))
