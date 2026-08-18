# -*- coding: utf-8 -*-
"""Сколько весит кэш страниц и какая его часть уже отработана.

Считаем ТРИ группы:
  отработан    паспорт текущего формата (format>=2) есть и непустой;
  в работе     паспорта нет / старый формат / отложен — кэш ещё нужен;
  сирота       файла соответствует ИНН, которого нет в companies.
Дополнительно — сколько среди «отработанных» тех, у кого привязка доказана
уликами (их удаление безвозвратно потеряет доказательство).
"""
import json
import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
KESH = os.environ.get('PAGECACHE_DIR', r'C:\seostat\drop\pagecache')
c = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/enrich.db', uri=True)
паспорт = {}
for inn, fj, fmt in c.execute(
        "select inn, coalesce(facts_json,''), coalesce(format,0) from site_facts"):
    паспорт[str(inn)] = (bool(fj), fmt)
есть_в_базе = {str(r[0]) for r in c.execute('select inn from companies')}
c.close()

итог = {'файлов': 0, 'байт': 0, 'группы': {}}
by = {}
for имя in os.listdir(KESH):
    if not имя.endswith('.json.gz'):
        continue
    inn = имя[:-8]
    try:
        n = os.path.getsize(os.path.join(KESH, имя))
    except OSError:
        continue
    итог['файлов'] += 1
    итог['байт'] += n
    есть, fmt = паспорт.get(inn, (False, 0))
    if inn not in есть_в_базе:
        г = 'сирота (ИНН нет в companies)'
    elif есть and fmt >= 2:
        г = 'отработан (паспорт текущего формата)'
    elif есть:
        г = 'паспорт старого формата — нужен переразбор'
    else:
        г = 'паспорта нет — кэш в работе'
    d = by.setdefault(г, {'файлов': 0, 'байт': 0})
    d['файлов'] += 1
    d['байт'] += n
итог['группы'] = {k: {'файлов': v['файлов'], 'ГБ': round(v['байт'] / 2**30, 2)}
                  for k, v in sorted(by.items(), key=lambda x: -x[1]['байт'])}
итог['всего_ГБ'] = round(итог['байт'] / 2**30, 2)
итог.pop('байт')
# место на диске
try:
    import shutil
    u = shutil.disk_usage(KESH)
    итог['диск'] = {'всего_ГБ': round(u.total / 2**30), 'свободно_ГБ': round(u.free / 2**30)}
except Exception as e:  # noqa: BLE001
    итог['диск'] = str(e)
print(json.dumps(итог, ensure_ascii=False, indent=1))
