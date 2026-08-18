# -*- coding: utf-8 -*-
"""Состав догруза: откуда взялись 1440, нет ли в них стоп-листа и конкурентов."""
import json
import sqlite3
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
ENRICH = r'C:\sender\enrich.db'
SENDER = r'C:\sender\sender.db'
САЙТ = "(e.source in ('own-site','zenno') or e.source like 'сайт:%')"
ЧИСТ = ("coalesce(e.pometka,'') not like '%спам-ловушк%' "
        "and coalesce(e.pometka,'') not like '%скрыт%' "
        "and coalesce(e.pometka,'') not like '%не использовать%'")

c = sqlite3.connect('file:%s?mode=ro' % ENRICH.replace('\\', '/'), uri=True)
c.row_factory = sqlite3.Row
годные = {}
for r in c.execute(
        "select k.inn, coalesce(nullif(k.short_name,''),k.name,'') name, "
        "coalesce(k.region,'') region, coalesce(k.okved,'') okved, "
        "coalesce(k.best_email,'') best, coalesce(k.is_competitor,0) konk, "
        "coalesce(k.nash_priznak,'') nash, coalesce(k.updated_at,'') upd "
        'from companies k where exists(select 1 from emails e where e.inn=k.inn '
        'and %s and %s) and exists(select 1 from site_facts f where f.inn=k.inn '
        'and coalesce(f.format,0)>=2 and f.facts_json like \'%%"продукция": ["%%\')'
        % (САЙТ, ЧИСТ)):
    годные[str(r['inn'])] = dict(r)
ts_паспорта = {str(r[0]): (r[1] or '') for r in c.execute(
    "select inn, ts from site_facts where coalesce(facts_json,'')<>''")}
чужие = set()
try:
    чужие = {str(r[0]) for r in c.execute(
        "select inn from prigovor_domenov where verdikt='чужой'")}
except Exception:  # noqa: BLE001
    pass
c.close()

s = sqlite3.connect('file:%s?mode=ro' % SENDER.replace('\\', '/'), uri=True)
s.row_factory = sqlite3.Row
в_группе, был_убран, чей_адрес = set(), set(), {}
for r in s.execute("select coalesce(inn,'') inn, lower(coalesce(email,'')) em, "
                   "coalesce(extra_json,'') ex from recipients"):
    инн = ''.join(ch for ch in r['inn'] if ch.isdigit())
    if r['em']:
        чей_адрес[r['em']] = инн
    if 'Партия 935' in r['ex']:
        в_группе.add(инн)
    if 'gruppy_ubrano' in r['ex']:
        был_убран.add(инн)
стоп_инн = {''.join(ch for ch in str(r[0]) if ch.isdigit()): (r[1] or '')
            for r in s.execute("select value, reason from suppression where scope='inn'")}
стоп_дом = {str(r[0]).lower() for r in s.execute(
    "select value from suppression where scope='domain'")}
s.close()

новые = {i: v for i, v in годные.items() if i not in в_группе and i not in чужие}
итог = {'новых': len(новые), 'откуда': {}, 'риски': {}}
for i, v in новые.items():
    к = ('был выведен чисткой, снова проходит' if i in был_убран else
         'паспорт собран 17-18.08 (обход шёл после заливки)'
         if ts_паспорта.get(i, '') >= '2026-08-17T12' else
         'адрес был занят другой группой на момент заливки'
         if v['best'] and чей_адрес.get(v['best'].lower(), i) != i else
         'прочее')
    итог['откуда'][к] = итог['откуда'].get(к, 0) + 1
итог['риски'] = {
    'в_стоп-листе_по_ИНН': sum(1 for i in новые if i in стоп_инн),
    'домен_почты_в_стоп-листе': sum(
        1 for v in новые.values()
        if v['best'] and v['best'].split('@')[-1].lower() in стоп_дом),
    'помечены_конкурентом': sum(1 for v in новые.values()
                                if str(v['konk']).strip().lower() in ('1', 'true', 'да')),
    'с_признаком_наш': sum(1 for v in новые.values()
                           if v['nash'] not in ('', 'нет', 'неизвестно'))}
итог['примеры'] = [{'инн': i, 'имя': v['name'][:38], 'регион': v['region'][:22],
                    'почта': v['best']} for i, v in list(новые.items())[:6]]
print(json.dumps(итог, ensure_ascii=False, indent=1))
