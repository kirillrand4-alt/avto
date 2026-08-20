# -*- coding: utf-8 -*-
r"""Что вообще лежит в паспортах, где «продукция» пуста и прочие поля тоже."""
import json
import sqlite3

ПОЛЯ = ('оборудование_линии', 'сырьё', 'мощности', 'энергохозяйство', 'газы',
        'упаковка_фасовка', 'контроль_качества', 'экспорт', 'клиенты',
        'расширение', 'новости', 'масштаб', 'география_поставок')
c = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=60)
c.row_factory = sqlite3.Row
ключи, увер, примеры, всего = {}, {}, [], 0
for r in c.execute("select inn, coalesce(site,'') site, facts_json f from site_facts "
                   "where coalesce(facts_json,'')<>'' and coalesce(format,0)>=2"):
    try:
        д = json.loads(r['f'])
    except Exception:  # noqa: BLE001
        continue
    if (д.get('продукция') or []) or any(д.get(п) for п in ПОЛЯ):
        continue
    всего += 1
    увер[str(д.get('уверенность'))] = увер.get(str(д.get('уверенность')), 0) + 1
    for k, v in д.items():
        if v not in (None, '', [], {}):
            ключи[k] = ключи.get(k, 0) + 1
    if len(примеры) < 6:
        примеры.append({'инн': str(r['inn']), 'сайт': r['site'][:44],
                        'непустые': [k for k, v in д.items()
                                     if v not in (None, '', [], {})][:6],
                        'цитата': str(д.get('цитата') or '')[:70]})
c.close()
print(json.dumps({'примеры': примеры}, ensure_ascii=False, indent=1))
print(json.dumps({'таких_паспортов': всего,
                  'непустые_ключи': dict(sorted(ключи.items(), key=lambda x: -x[1])),
                  'уверенность': увер}, ensure_ascii=False, indent=1))
