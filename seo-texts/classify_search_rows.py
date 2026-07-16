# -*- coding: utf-8 -*-
"""Построчная классификация проблемных запросов: реальная боль внутреннего поиска или артефакт."""
import csv, json, re
from concurrent.futures import ThreadPoolExecutor, as_completed

from gen_provider import make_client, call

rows = list(csv.DictReader(open('inventory/search-problems.csv', encoding='utf-8-sig'), delimiter=';'))
internal = [json.loads(l)['phrase'] for l in open('inventory/search-results.jsonl') if json.loads(l)['source'] == 'site']

PROMPT = """Реальный внутренний поиск магазина промышленных компрессоров выглядит так
(живые фразы пользователей на сайте): {examples}

Ниже - проблемные запросы из теста. Для КАЖДОГО реши:
- realistic: true, если фразу такого ТИПА мог бы ввести человек в строку поиска ПО САЙТУ
  (модель, бренд, категория, характеристика; также допускай вставку запроса из поисковика
  целиком - это случается, но помечай пометкой paste)
- pattern: [model / brand / category / spec / paste_from_serp / unrealistic]

Запросы (JSON): {batch}

Ответ - ОДИН JSON-массив в том же порядке: [{{"phrase":"...","realistic":bool,"pattern":"..."}}]"""

client = make_client()

def worker(ib):
    i, batch = ib
    prompt = PROMPT.format(examples=json.dumps(internal[:60], ensure_ascii=False),
                           batch=json.dumps([r['Запрос'] for r in batch], ensure_ascii=False))
    msg = call(client, [{'role': 'user', 'content': prompt}], 'claude-fable-5')
    text = ''.join(b.text for b in msg.content if b.type == 'text')
    m = re.search(r'\[.*\]', text, re.S)
    print(f'батч {i+1} ок', flush=True)
    return json.loads(m.group(0))

B = 30
batches = [rows[i:i+B] for i in range(0, len(rows), B)]
res = [None]*len(batches)
with ThreadPoolExecutor(max_workers=8) as ex:
    futs = {ex.submit(worker, (i, b)): i for i, b in enumerate(batches)}
    for f in as_completed(futs):
        try: res[futs[f]] = f.result()
        except Exception as e: print(f'батч {futs[f]+1} FAIL {repr(e)[:100]}', flush=True)

flat = [x for r in res if r for x in r]
json.dump(flat, open('inventory/rows-classified.json', 'w'), ensure_ascii=False, indent=1)
from collections import Counter
print('ИТОГО:', len(flat), Counter(x['pattern'] for x in flat).most_common())
