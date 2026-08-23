# -*- coding: utf-8 -*-
r"""Кто из паспортных с адресом ещё не в группе и по какой причине."""
import json
import re
import sqlite3

ТВЁРДЫЕ = ('оборудование_линии', 'энергохозяйство', 'газы', 'мощности', 'сырьё',
           'упаковка_фасовка', 'контроль_качества', 'расширение')
МЯГКИЕ = ('новости', 'масштаб', 'география_поставок', 'экспорт', 'клиенты')
ВЛАСТЬ = re.compile(r'АДМИНИСТРАЦИЯ|СОВЕТ ДЕПУТАТОВ|СЕЛЬСОВЕТ|ГОРОДСКОЙ ОКРУГ|'
                    r'МУНИЦИПАЛЬНОГО РАЙОНА|УПРАВЛЕНИЕ ДЕЛАМИ|КОМИТЕТ ПО ', re.I)
ШКОЛА = re.compile(r'\bШКОЛА|ЛИЦЕЙ|ГИМНАЗИЯ|ДЕТСКИЙ САД|УНИВЕРСИТЕТ|КОЛЛЕДЖ|'
                   r'ТЕХНИКУМ', re.I)

s = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True, timeout=60)
в_группе = set()
for инн, ex in s.execute("select coalesce(inn,''), coalesce(extra_json,'') from recipients"):
    if 'Партия 935' in ex:
        ц = ''.join(c for c in str(инн) if c.isdigit())
        if ц:
            в_группе.add(ц)
стоп = {''.join(c for c in str(r[0]) if c.isdigit()) for r in
        s.execute("select value from suppression where scope='inn'")}
s.close()

e = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=60)
чистый = {str(r[0]) for r in e.execute(
    "select distinct e.inn from emails e where (e.source in ('own-site','zenno') "
    "or e.source like 'сайт:%') and coalesce(e.pometka,'') not like '%спам-ловушк%' "
    "and coalesce(e.pometka,'') not like '%скрыт%' "
    "and coalesce(e.pometka,'') not like '%не использовать%'")}
имена = {str(r[0]): (r[1] or '', r[2] or '') for r in e.execute(
    "select inn, coalesce(nullif(short_name,''),name,''), coalesce(okved,'') "
    'from companies')}
ст = {'всего': 0, 'твёрдый_материал': 0, 'только_мягкое': 0, 'паспорт_пуст': 0,
      'власть_или_школа': 0, 'в_стоп_листе': 0}
примеры = []
for инн, f in e.execute("select inn, facts_json from site_facts "
                        "where coalesce(facts_json,'')<>'' and coalesce(format,0)>=2"):
    и = str(инн)
    if и in в_группе or и not in чистый:
        continue
    try:
        д = json.loads(f)
    except Exception:  # noqa: BLE001
        continue
    ст['всего'] += 1
    нм, ок = имена.get(и, ('', ''))
    if и in стоп:
        ст['в_стоп_листе'] += 1
        continue
    if ок.startswith(('84', '85')) or ВЛАСТЬ.search(нм) or ШКОЛА.search(нм):
        ст['власть_или_школа'] += 1
        continue
    if д.get('продукция') or any(д.get(п) for п in ТВЁРДЫЕ):
        ст['твёрдый_материал'] += 1
        if len(примеры) < 5:
            примеры.append({'инн': и, 'имя': нм[:40]})
    elif any(д.get(п) for п in МЯГКИЕ):
        ст['только_мягкое'] += 1
    else:
        ст['паспорт_пуст'] += 1
e.close()
print(json.dumps({'примеры_твёрдых': примеры}, ensure_ascii=False, indent=1)[:700])
print(json.dumps({'остаток': ст}, ensure_ascii=False, indent=1))
