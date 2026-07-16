# -*- coding: utf-8 -*-
"""Извлечение фактов из ОСТАЛЬНЫХ листов прайса (осушители, фильтры, ресиверы, генераторы газов,
пропущенные компрессоры) через Fable API. Обобщённый промпт под любой тип оборудования."""
import json, re
from concurrent.futures import ThreadPoolExecutor, as_completed
from gen_provider import make_client, call

rest = json.load(open('katalogi/rest-sheets.json'))

PROMPT = """Ты извлекаешь факты для базы знаний интернет-магазина промышленного оборудования
для сжатого воздуха (компрессоры, осушители реф./адсорбц., фильтры, ресиверы, генераторы
азота/кислорода, сепараторы, расходники). Ниже - строки листа прайса «Компрессор Центр».
Сначала определи ТИП оборудования на листе и извлекай факты, релевантные этому типу.

Лист: «{sheet}»
Строки: {rows}

Извлеки СТРОГО из данных (не выдумывай):
- product_type: тип оборудования (компрессор винтовой/поршневой/дизельный; осушитель реф./адсорбц.;
  фильтр; ресивер; генератор азота/кислорода; и т.п.)
- brand: бренд
- series: серии/префиксы с расшифровкой, ЕСЛИ выводится из данных
- key_specs: какие характеристики есть в листе (для компрессора: мощность/давление/производ./блок;
  для осушителя: производит./точка росы/тип; для ресивера: объём/давление; для генератора: чистота/производит.)
- marking_rules: правила маркировки, однозначно видные из сопоставления модель↔характеристики
- dependencies: закономерности «параметр зависит от мощности/серии/типоразмера» (если есть)
- ranges: числовые диапазоны ключевых характеристик
- notes: аномалии, на что обратить внимание копирайтеру
- confidence: high/medium/low

Ответь ОДНИМ JSON с этими полями."""

client = make_client()

def worker(it):
    d = json.load(open(it['file']))
    prompt = PROMPT.format(sheet=it['sheet'], rows=json.dumps(d['rows'][:100], ensure_ascii=False)[:12000])
    msg = call(client, [{'role': 'user', 'content': prompt}], 'claude-fable-5')
    text = ''.join(b.text for b in msg.content if b.type == 'text')
    m = re.search(r'\{.*\}', text, re.S)
    res = json.loads(m.group(0)); res['_sheet'] = it['sheet']
    print(f"ок: {it['sheet']}", flush=True)
    return res

results = []
with ThreadPoolExecutor(max_workers=8) as ex:
    futs = {ex.submit(worker, it): it for it in rest}
    for f in as_completed(futs):
        try: results.append(f.result())
        except Exception as e: print(f"FAIL {futs[f]['sheet']}: {repr(e)[:100]}", flush=True)

json.dump(results, open('katalogi/kb-enrichment-rest.json', 'w'), ensure_ascii=False, indent=1)
print('ИЗВЛЕЧЕНО (остальные):', len(results))
