# -*- coding: utf-8 -*-
r"""Только счёт по «продукции» — без примеров, чтобы сводка не срезалась."""
import json
import sqlite3

BD = 'file:C:/sender/enrich.db?mode=ro'
ПОЛЯ = ('оборудование_линии', 'сырьё', 'мощности', 'энергохозяйство', 'газы',
        'упаковка_фасовка', 'контроль_качества', 'экспорт', 'клиенты',
        'расширение', 'новости', 'масштаб', 'география_поставок')
c = sqlite3.connect(BD, uri=True, timeout=60)
ст = {'паспортов_формат2': 0, 'продукция_есть': 0, 'продукция_пуста': 0,
      'пуста_но_есть_другое': 0, 'пуст_весь_паспорт': 0, 'битый_json': 0}
строк = []
for inn, f in c.execute("select inn, facts_json from site_facts "
                        "where coalesce(facts_json,'')<>'' and coalesce(format,0)>=2"):
    ст['паспортов_формат2'] += 1
    try:
        д = json.loads(f)
    except Exception:  # noqa: BLE001
        ст['битый_json'] += 1
        continue
    прод = д.get('продукция') or []
    if прод:
        ст['продукция_есть'] += 1
        строк.append(len(прод))
    else:
        ст['продукция_пуста'] += 1
        if any(д.get(п) for п in ПОЛЯ):
            ст['пуста_но_есть_другое'] += 1
        else:
            ст['пуст_весь_паспорт'] += 1
ст['всего_записей_site_facts'] = c.execute('select count(*) from site_facts').fetchone()[0]
ст['старый_формат_или_пусто'] = c.execute(
    "select count(*) from site_facts where coalesce(facts_json,'')='' "
    'or coalesce(format,0)<2').fetchone()[0]
c.close()
ст['строк_продукции_в_среднем'] = round(sum(строк) / max(1, len(строк)), 1)
ст['доля_пустых_проц'] = round(
    100.0 * ст['продукция_пуста'] / max(1, ст['паспортов_формат2']), 1)
print(json.dumps(ст, ensure_ascii=False, indent=1))
