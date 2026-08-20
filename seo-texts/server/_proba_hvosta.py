# -*- coding: utf-8 -*-
r"""Хвост очереди: работает ли переразбор, когда новых компаний не осталось.

Прямая проба ничего не показывает — новых компаний в кэше сейчас навалом, и
отбор честно набирает батч из них. Чтобы проверить сам механизм, подсовываем
отбору «всё уже разобрано»: тогда единственные кандидаты — устаревшие паспорта.
"""
import json
import sqlite3
import sys
import time

sys.path.insert(0, r'C:\sender\server')
import site_facts as SF  # noqa: E402

c = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=60)
готовые = {str(x[0]) for x in c.execute(
    "select inn from site_facts where coalesce(popytok,0) >= 3 "
    "or coalesce(otlozheno_do,0) > ? "
    "or (coalesce(facts_json,'')<>'' and coalesce(format,0) >= ?)",
    (time.time(), SF.FORMAT))}
свежесть = {str(x[0]): SF._vremya_pasporta(x[1]) for x in c.execute(
    "select inn, coalesce(ts,'') from site_facts where coalesce(facts_json,'')<>''")}
все_инн = {str(x[0]) for x in c.execute('select inn from companies')}
c.close()

# «Всё разобрано»: новых кандидатов нет вовсе, остаются только устаревшие.
как_будто = готовые | все_инн
партия = SF._iz_kesha(50, как_будто, свежесть)
komp = [k for k in партия if k.get('pererazbor') or k['inn'] not in готовые]
print(json.dumps({
    'кандидатов': len(партия),
    'из_них_на_переразбор': sum(1 for k in партия if k.get('pererazbor')),
    'дошло_бы_до_разбора': len(komp),
    'пример': [{'инн': k['inn'], 'сайт': k['site'][:40]} for k in партия[:3]],
}, ensure_ascii=False, indent=1))
