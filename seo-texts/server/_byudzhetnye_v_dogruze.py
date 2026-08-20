# -*- coding: utf-8 -*-
r"""Сколько в «твёрдых 300» бюджетных контор и кто именно.

Администрация района — не цель компрессорного письма ни при каком паспорте.
Больница — цель спорная, но настоящая: кислородная станция и медицинский
воздух покупаются. Поэтому считаем отдельно органы власти/образование и
отдельно здравоохранение, чтобы решать не на глаз.
"""
import json
import re
import sqlite3

ТВЁРДЫЕ = ('оборудование_линии', 'энергохозяйство', 'газы', 'мощности', 'сырьё',
           'упаковка_фасовка', 'контроль_качества', 'расширение')
ВЛАСТЬ = re.compile(r'АДМИНИСТРАЦИЯ|СОВЕТ ДЕПУТАТОВ|СЕЛЬСОВЕТ|ГОРОДСКОЙ ОКРУГ|'
                    r'МУНИЦИПАЛЬНОГО РАЙОНА|УПРАВЛЕНИЕ ДЕЛАМИ|КОМИТЕТ ПО ', re.I)
ШКОЛА = re.compile(r'\bШКОЛА|ЛИЦЕЙ|ГИМНАЗИЯ|ДЕТСКИЙ САД|УНИВЕРСИТЕТ|КОЛЛЕДЖ|ТЕХНИКУМ', re.I)
c = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=60)
c.row_factory = sqlite3.Row
имена = {str(r['inn']): (r['nm'], r['ok'])
         for r in c.execute("select inn, coalesce(nullif(short_name,''),name,'') nm, "
                            "coalesce(okved,'') ok from companies")}
ст = {'твёрдых': 0, 'власть': 0, 'образование': 0, 'здравоохранение': 0,
      'прочие': 0}
примеры = {'власть': [], 'образование': [], 'здравоохранение': []}
for i, f in c.execute("select inn, facts_json from site_facts "
                      "where coalesce(facts_json,'')<>'' and coalesce(format,0)>=2"):
    try:
        д = json.loads(f)
    except Exception:  # noqa: BLE001
        continue
    if д.get('продукция') or not any(д.get(п) for п in ТВЁРДЫЕ):
        continue
    ст['твёрдых'] += 1
    нм, ок = имена.get(str(i), ('', ''))
    вид = 'прочие'
    if ок.startswith('84') or ВЛАСТЬ.search(нм):
        вид = 'власть'
    elif ок.startswith('85') or ШКОЛА.search(нм):
        вид = 'образование'
    elif ок.startswith('86') or ок.startswith('87'):
        вид = 'здравоохранение'
    ст[вид] += 1
    if вид != 'прочие' and len(примеры[вид]) < 4:
        примеры[вид].append({'инн': str(i), 'имя': нм[:44], 'оквэд': ок[:28]})
c.close()
print(json.dumps({'примеры': примеры}, ensure_ascii=False, indent=1))
print(json.dumps({'счёт': ст}, ensure_ascii=False, indent=1))
