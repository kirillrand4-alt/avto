# -*- coding: utf-8 -*-
"""Чем ещё связать `company_id` площадки с ИНН — узкое место сместилось сюда.

Разбор 9 335 карточек дал 94 технаря с личным мобильным, но предприятие опознано
только у 21: связь «id компании на площадке → ИНН» берётся из словаря `компании`
выгрузки соседа, а он покрывает не всех. То есть люди добыты, а к кому они относятся
— наполовину неизвестно. Это не потеря данных: строки лежат с названием компании,
просто без ИНН их не сшить ни с продажами, ни с центробежностью.

У сборщика (`tenderpro_harvest.py --inn`) режим для этого есть: ИНН напечатан на
странице `/api/company/<cid>/view`. Прибор ищет, не собран ли этот словарь уже.
"""
import csv
import glob
import json
import os

csv.field_size_limit(10 ** 8)
puti = []
for shabl in (r'C:\seostat\drop\drop-storage\tp-inn*.csv', r'C:\sender\**\tp-inn*.csv',
              r'C:\seostat\**\tp-inn*.csv', r'C:\seostat\drop\drop-storage\tp-*.csv'):
    puti += glob.glob(shabl, recursive=True)

itog = {}
for p in sorted(set(puti)):
    try:
        with open(p, encoding='utf-8-sig', newline='') as f:
            r = csv.DictReader(f, delimiter=';')
            polya = r.fieldnames or []
            rows = list(r)
        s_inn = sum(1 for x in rows
                    if any(k and 'inn' in k.lower() and (x.get(k) or '').strip()
                           for k in polya))
        print('%s\n    строк %d, с ИНН %d\n    поля: %s'
              % (os.path.basename(p), len(rows), s_inn, ', '.join(polya)))
        itog[os.path.basename(p)] = {'строк': len(rows), 'с ИНН': s_inn}
    except Exception as e:  # noqa: BLE001
        print('%s -> %s' % (p, e))
print('ИТОГ ' + json.dumps(itog, ensure_ascii=False))
