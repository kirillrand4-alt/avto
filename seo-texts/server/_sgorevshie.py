# -*- coding: utf-8 -*-
"""Сколько карточек выбыло из разбора из-за падений провайдера, а не из-за сайта."""
import json
import sqlite3
import sys

c = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/enrich.db', uri=True)
c.row_factory = sqlite3.Row
итог = {}
итог['пустых_карточек'] = c.execute(
    "select count(*) from site_facts where coalesce(facts_json,'')=''").fetchone()[0]
итог['из_них_попыток_3_и_больше'] = c.execute(
    "select count(*) from site_facts where coalesce(facts_json,'')='' "
    'and coalesce(popytok,0) >= 3').fetchone()[0]
итог['с_ошибкой_провайдера'] = c.execute(
    "select count(*) from site_facts where note like 'провайдер:%'").fetchone()[0]
итог['сгорели_на_провайдере'] = c.execute(
    "select count(*) from site_facts where note like 'провайдер:%' "
    'and coalesce(popytok,0) >= 3').fetchone()[0]
итог['по_текстам_ошибок'] = [dict(r) for r in c.execute(
    "select substr(note,1,80) oshibka, count(*) skolko, max(popytok) popytok "
    "from site_facts where note like 'провайдер:%' group by substr(note,1,60) "
    'order by skolko desc limit 8')]
итог['страниц_нет'] = c.execute(
    "select count(*) from site_facts where note='страниц в кэше нет'").fetchone()[0]
c.close()
sys.stdout.reconfigure(encoding='utf-8')
print(json.dumps(итог, ensure_ascii=False, indent=1))
