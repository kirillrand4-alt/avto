# -*- coding: utf-8 -*-
"""Извлечение фактов для базы знаний из листов прайса КЦ через Fable API, параллельно."""
import json, re
from concurrent.futures import ThreadPoolExecutor, as_completed

from gen_provider import make_client, call

rel = json.load(open('katalogi/relevant-sheets.json'))

PROMPT = """Ты извлекаешь факты для базы знаний интернет-магазина промышленных компрессоров.
Ниже - строки листа прайса «Компрессор Центр» (модели с характеристиками). Первые строки часто
заголовки-разделители (тип привода, ступени сжатия и т.п.), потом строка с названиями колонок,
потом модели.

Лист: «{sheet}»
Строки (массив массивов ячеек):
{rows}

Извлеки СТРОГО из этих данных (ничего не выдумывай, если чего-то нет - не пиши):
- brand: бренд
- series: список серий/префиксов моделей с их расшифровкой, ЕСЛИ она выводится из данных
  (напр. буква = винтовой блок BAOSI/HANBELL; суффикс = привод/частотник/ресивер)
- marking_rules: правила маркировки, которые ОДНОЗНАЧНО видны из сопоставления модель↔характеристики
- dependencies: закономерности вида «параметр X зависит от мощности/серии»
  (напр. класс защиты IP, тип привода ременной/прямой, тип блока - при каком диапазоне мощности что)
- ranges: диапазоны мощность/давление/производительность по листу
- blocks_engines: какие винтовые блоки/двигатели упоминаются у каких серий
- notes: аномалии, странности, на что обратить внимание копирайтеру
- confidence: overall уверенность high/medium/low

Ответь ОДНИМ JSON с этими полями."""

client = make_client()

def worker(it):
    d = json.load(open(it['file']))
    rows = d['rows'][:120]  # шапки + достаточно моделей для паттернов
    prompt = PROMPT.format(sheet=it['sheet'], rows=json.dumps(rows, ensure_ascii=False)[:12000])
    msg = call(client, [{'role': 'user', 'content': prompt}], 'claude-fable-5')
    text = ''.join(b.text for b in msg.content if b.type == 'text')
    m = re.search(r'\{.*\}', text, re.S)
    res = json.loads(m.group(0))
    res['_sheet'] = it['sheet']
    print(f"ок: {it['sheet']}", flush=True)
    return res

results = []
with ThreadPoolExecutor(max_workers=8) as ex:
    futs = {ex.submit(worker, it): it for it in rel}
    for f in as_completed(futs):
        try: results.append(f.result())
        except Exception as e: print(f"FAIL {futs[f]['sheet']}: {repr(e)[:100]}", flush=True)

json.dump(results, open('katalogi/kb-enrichment.json', 'w'), ensure_ascii=False, indent=1)
print('ИЗВЛЕЧЕНО фактов по листам:', len(results))
