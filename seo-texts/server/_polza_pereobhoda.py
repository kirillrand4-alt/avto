# -*- coding: utf-8 -*-
"""Что автодолив очереди приносит СЕЙЧАС: новая работа или перемалывание того же.

Переобход завели 14.08: старый кубик брал «о компании» и контакты, а каталог,
производство, качество и проекты почти не открывал. Значит польза переобхода
делится на две разные вещи:
  РАЗОВАЯ  — компании, которых новый кубик ещё не касался; у них появятся разделы,
             которых в кэше нет вовсе;
  ПОСТОЯННАЯ — свежесть: новости и изменения на уже обойденных сайтах.

Здесь считаем, сколько осталось первой — это и есть ответ, нужен ли автодолив.
"""
import json
import os
import sqlite3
import sys
import time

KESH = os.environ.get('PAGECACHE_DIR', r'C:\seostat\drop\pagecache')
BD = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
# новый кубик с приоритетом разделов уехал на сервер 14.08 около 13:00
НОВЫЙ_КУБИК = time.mktime(time.strptime('2026-08-14 13:00', '%Y-%m-%d %H:%M'))

c = sqlite3.connect('file:%s?mode=ro' % BD.replace('\\', '/'), uri=True)
с_привязкой = {str(r[0]) for r in c.execute(
    "select inn from companies where coalesce(site,'')<>'' or coalesce(cand_site,'')<>''")}
c.close()

есть_кэш, старый, новый = set(), 0, 0
for имя in os.listdir(KESH):
    if not имя.endswith('.json.gz'):
        continue
    inn = имя.split('.')[0]
    есть_кэш.add(inn)
    if inn not in с_привязкой:
        continue
    if os.path.getmtime(os.path.join(KESH, имя)) >= НОВЫЙ_КУБИК:
        новый += 1
    else:
        старый += 1

sys.stdout.reconfigure(encoding='utf-8')
print(json.dumps({
    'компаний_с_привязкой': len(с_привязкой),
    'из_них_ни_разу_не_обойдены': len(с_привязкой - есть_кэш),
    'обойдены_старым_кубиком_до_14.08': старый,
    'обойдены_новым_кубиком': новый,
    'разовой_работы_осталось': len(с_привязкой - есть_кэш) + старый,
}, ensure_ascii=False, indent=1))
