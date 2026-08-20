# -*- coding: utf-8 -*-
r"""1342 компании с готовым паспортом, чей адрес НЕ с их сайта: откуда он.

Это следующий рычаг после паспортов: письмо писать есть о чём, а слать некуда.
Источник адреса решает, годится он или нет — адрес из справочника и адрес с
контактной страницы сайта живут по разным правилам.
"""
import json
import sqlite3
import sys

sys.path.insert(0, r'C:\sender\server')
import dogruz_935 as D  # noqa: E402

c = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=60)
с_продукцией = {str(r[0]) for r in c.execute(
    "select inn from site_facts where coalesce(format,0)>=2 "
    "and facts_json like '%\"продукция\": [\"%'")}
с_сайта = {str(r[0]) for r in c.execute(
    'select distinct e.inn from emails e where %s and %s' % (D.САЙТ, D.ЧИСТ))}
цель = с_продукцией - с_сайта
источники, пометки = {}, {}
свои = 0
for инн, ист, пом in c.execute("select inn, coalesce(source,''), "
                               "coalesce(pometka,'') from emails"):
    if str(инн) not in цель:
        continue
    свои += 1
    источники[ист[:26] or '(пусто)'] = источники.get(ист[:26] or '(пусто)', 0) + 1
    if пом:
        пометки[пом[:36]] = пометки.get(пом[:36], 0) + 1
c.close()
print(json.dumps({'компаний_без_адреса_с_сайта': len(цель),
                  'адресов_у_них': свои,
                  'источники': dict(sorted(источники.items(),
                                           key=lambda x: -x[1])[:12]),
                  'пометки': dict(sorted(пометки.items(),
                                         key=lambda x: -x[1])[:8])},
                 ensure_ascii=False, indent=1))
