# -*- coding: utf-8 -*-
"""Что из добытого ещё НЕ доехало до карточки: снимок отстаёт от источника.

Панель читает `centrifugal.db` — это СНИМОК, собираемый из `enrich.db`. Всё, что залито в
источник после последней сборки, продавец не видит. Считаю разрыв по каждой сущности, а не
на глаз.
"""
import json
import sqlite3

src = sqlite3.connect(r'C:\sender\enrich.db')
sn = sqlite3.connect(r'C:\seostat\data\centrifugal.db')
o = {}
o['люди: в источнике enrich.db'] = src.execute('select count(*) from people').fetchone()[0]
o['люди: в снимке панели'] = sn.execute('select count(*) from person').fetchone()[0]
o['с телефоном: в источнике'] = src.execute(
    "select count(*) from people where coalesce(phone,'') <> ''").fetchone()[0]
o['с телефоном: в снимке'] = sn.execute(
    "select count(*) from person where coalesce(phone,'') <> ''").fetchone()[0]
try:
    o['когда собран снимок'] = dict(sn.execute('select key, value from import_info')).get(
        'built_at') or dict(sn.execute('select key, value from import_info'))
except Exception as e:  # noqa: BLE001
    o['когда собран снимок'] = str(e)[:80]
print(json.dumps(o, ensure_ascii=False, indent=1))
