# -*- coding: utf-8 -*-
r"""Из чего состоят 404 «без продукции»: чем именно подтверждён материал.

Прежде чем заливать, надо знать, кого заливаем. «Любое непустое поле» пускает
внутрь администрации районов и ЦРБ — у них на сайте есть новости, и формально
это «материал». Для компрессорного письма материалом является совсем другое.
"""
import json
import sqlite3

ТВЁРДЫЕ = ('оборудование_линии', 'энергохозяйство', 'газы', 'мощности', 'сырьё',
           'упаковка_фасовка', 'контроль_качества', 'расширение')
МЯГКИЕ = ('новости', 'масштаб', 'география_поставок', 'экспорт', 'клиенты')
c = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=60)
c.row_factory = sqlite3.Row
имена = {}
for r in c.execute("select inn, coalesce(nullif(short_name,''),name,'') nm, "
                   "coalesce(division,'') d, coalesce(okved,'') ok from companies"):
    имена[str(r['inn'])] = (r['nm'], r['d'], r['ok'])

ст = {'всего': 0, 'есть_твёрдое': 0, 'только_мягкое': 0}
поля_счёт, див, примеры_т, примеры_м = {}, {}, [], []
for i, f in c.execute("select inn, facts_json from site_facts "
                      "where coalesce(facts_json,'')<>'' and coalesce(format,0)>=2"):
    try:
        д = json.loads(f)
    except Exception:  # noqa: BLE001
        continue
    if д.get('продукция'):
        continue
    т = [п for п in ТВЁРДЫЕ if д.get(п)]
    м = [п for п in МЯГКИЕ if д.get(п)]
    if not (т or м):
        continue
    ст['всего'] += 1
    нм, d, ok = имена.get(str(i), ('', '', ''))
    for п in т + м:
        поля_счёт[п] = поля_счёт.get(п, 0) + 1
    if т:
        ст['есть_твёрдое'] += 1
        див[d or '(пусто)'] = див.get(d or '(пусто)', 0) + 1
        if len(примеры_т) < 5:
            примеры_т.append({'инн': str(i), 'имя': нм[:46], 'напр': d,
                              'поля': т[:4]})
    else:
        ст['только_мягкое'] += 1
        if len(примеры_м) < 5:
            примеры_м.append({'инн': str(i), 'имя': нм[:46], 'поля': м[:4]})
c.close()
print(json.dumps({'примеры_твёрдые': примеры_т, 'примеры_мягкие': примеры_м},
                 ensure_ascii=False, indent=1))
print(json.dumps({'счёт': ст, 'поля': dict(sorted(поля_счёт.items(),
                                                  key=lambda x: -x[1])),
                  'направления_у_твёрдых': див}, ensure_ascii=False, indent=1))
