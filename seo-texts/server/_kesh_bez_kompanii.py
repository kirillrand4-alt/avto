# -*- coding: utf-8 -*-
"""Почему разбор простаивает, когда обход идёт: чьи страницы приезжают в кэш."""
import json
import os
import sqlite3
import sys
import time

KESH = r'C:\seostat\drop\pagecache'
c = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/enrich.db', uri=True)
в_базе = {str(r[0]) for r in c.execute('select inn from companies')}
с_привязкой = {str(r[0]) for r in c.execute(
    "select inn from companies where coalesce(site,'')<>'' or coalesce(cand_site,'')<>''")}
c.close()
сейчас = time.time()
свежие, нет_строки, без_привязки, годные = 0, 0, 0, 0
примеры = []
for имя in os.listdir(KESH):
    if not имя.endswith('.json.gz'):
        continue
    if сейчас - os.path.getmtime(os.path.join(KESH, имя)) > 3 * 3600:
        continue
    свежие += 1
    inn = имя.split('.')[0]
    if inn not in в_базе:
        нет_строки += 1
        if len(примеры) < 6:
            примеры.append(inn)
    elif inn not in с_привязкой:
        без_привязки += 1
    else:
        годные += 1
sys.stdout.reconfigure(encoding='utf-8')
print(json.dumps({'обойдено_за_3_часа': свежие,
                  'нет_строки_в_companies': нет_строки,
                  'строка_есть_но_без_привязки': без_привязки,
                  'годны_к_разбору': годные,
                  'примеры_инн_без_строки': примеры}, ensure_ascii=False, indent=1))
