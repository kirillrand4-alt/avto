# -*- coding: utf-8 -*-
"""Работает ли отмена готовности: берёт ли разбор компании со свежим кэшем."""
import json
import os
import sqlite3
import sys
import time

sys.path.insert(0, r'C:\sender\server')
import site_facts as SF  # noqa: E402

c = sqlite3.connect('file:%s?mode=ro' % SF.BD.replace('\\', '/'), uri=True)
svezhest = {str(r[0]): SF._vremya_pasporta(r[1]) for r in c.execute(
    "select inn, coalesce(ts,'') from site_facts where coalesce(facts_json,'')<>''")}
gotovye = {str(r[0]) for r in c.execute(
    "select inn from site_facts where coalesce(popytok,0) >= 3 or coalesce(otlozheno_do,0) > ? "
    "or (coalesce(facts_json,'')<>'' and coalesce(format,0) >= ?)", (time.time(), SF.FORMAT))}
c.close()

взял = SF._iz_kesha(40, gotovye, svezhest)
# сколько из взятых — это ПЕРЕСБОРКА (паспорт есть, но кэш свежее)
пересборка = sum(1 for k in взял if k['inn'] in svezhest)
итог = {'разбор_возьмёт_сейчас': len(взял), 'из_них_пересборка_после_обхода': пересборка,
        'примеры': [{'инн': k['inn'], 'сайт': k['site'],
                     'паспорт_был': bool(svezhest.get(k['inn']))} for k in взял[:5]]}
# и то же самое БЕЗ учёта свежести — как было до правки
было = SF._iz_kesha(40, gotovye, None)
итог['взял_бы_старый_код'] = len(было)
sys.stdout.reconfigure(encoding='utf-8')
print(json.dumps(итог, ensure_ascii=False, indent=1))
