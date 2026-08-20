# -*- coding: utf-8 -*-
r"""Воронка: 9571 паспорт с продукцией → сколько реально в панели и почему.

Вопрос владельца 20.08 — «почему продукция есть у 9,6к, а залили только 85».
Считаем каждый шаг отдельно, чтобы было видно, где теряются компании.
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
любой_адрес = {str(r[0]) for r in c.execute('select distinct inn from emails')}
c.close()

s = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True, timeout=60)
в_панели, в_группе = set(), set()
for инн, ex in s.execute("select coalesce(inn,''), coalesce(extra_json,'') "
                         'from recipients'):
    и = ''.join(ch for ch in str(инн) if ch.isdigit())
    if not и:
        continue
    в_панели.add(и)
    if D.ГРУППА in ex:
        в_группе.add(и)
s.close()

шаг = {
    '1_паспорт_с_продукцией': len(с_продукцией),
    '2_и_чистый_адрес_с_САЙТА': len(с_продукцией & с_сайта),
    '3_из_них_уже_в_группе': len(с_продукцией & с_сайта & в_группе),
    '4_из_них_в_панели_но_без_группы': len(
        (с_продукцией & с_сайта & в_панели) - в_группе),
}
потери = {
    'адрес_есть_но_НЕ_с_сайта': len((с_продукцией - с_сайта) & любой_адрес),
    'адреса_нет_вообще': len(с_продукцией - любой_адрес),
}
print(json.dumps({'воронка': шаг, 'почему_не_прошли': потери,
                  'в_группе_всего_инн': len(в_группе)},
                 ensure_ascii=False, indent=1))
