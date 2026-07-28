# -*- coding: utf-8 -*-
"""Дооценка фраз, чьи батчи упали в search_eval.py. Тот же промпт, батчи меньше (10),
меньше параллельности; результат сливается в inventory/search-eval.json в порядке прогона."""
import json, re
from concurrent.futures import ThreadPoolExecutor, as_completed

from gen_provider import make_client, call

recs = [json.loads(l) for l in open('inventory/search-results.jsonl')]
done = {e['phrase']: e for e in json.load(open('inventory/search-eval.json'))}
todo = [r for r in recs if r['phrase'] not in done]
print('дооценка фраз:', len(todo))

PROMPT = """Ты аудитор внутреннего поиска интернет-магазина промышленных компрессоров prokompressor.ru
(винтовые, поршневые, дизельные компрессоры; осушители, ресиверы, фильтры, запчасти, генераторы газов).
Оцени, насколько выдача поиска отвечает на запрос ПОКУПАТЕЛЯ.

Для каждого запроса ниже дан список из топ-результатов (названия товаров, что реально показал поиск).
Оцени:
- relevance: 0 (мусор/пусто/нерелевантно) / 1 (частично, топ размыт) / 2 (точно отвечает интенту)
- should_have: true, если по такому запросу магазин компрессоров ОБЯЗАН что-то показывать
  (товар такого типа реально существует в этой тематике), false если запрос вне ассортимента
- fail_type: одно из [ok, empty_but_should, wrong_top, too_few, model_not_found, category_not_found, out_of_scope]
- note: 1 короткая фраза что не так (пусто если ok)

Запросы с их выдачей (JSON):
{batch}

Ответь ОДНИМ JSON-массивом в том же порядке: [{{"phrase":"...","relevance":N,"should_have":bool,"fail_type":"...","note":"..."}}]"""

client = make_client()

def worker(ib):
    i, batch = ib
    payload = [{'phrase': r['phrase'], 'found': r.get('found', 0),
                'top': [t['name'] for t in r.get('top', [])][:8]} for r in batch]
    msg = call(client, [{'role': 'user', 'content': PROMPT.format(batch=json.dumps(payload, ensure_ascii=False))}],
               'claude-fable-5')
    text = ''.join(b.text for b in msg.content if b.type == 'text')
    arr = json.loads(re.search(r'\[.*\]', text, re.S).group(0))
    print(f'добатч {i+1}: {len(arr)}', flush=True)
    return arr

B = 10
batches = [todo[i:i+B] for i in range(0, len(todo), B)]
res = [None] * len(batches)
with ThreadPoolExecutor(max_workers=4) as ex:
    futs = {ex.submit(worker, (i, b)): i for i, b in enumerate(batches)}
    for f in as_completed(futs):
        try: res[futs[f]] = f.result()
        except Exception as e: print(f'добатч {futs[f]+1} FAIL: {repr(e)[:120]}', flush=True)

for r in res:
    if r:
        for x in r:
            done[x['phrase']] = x

merged = [done[r['phrase']] for r in recs if r['phrase'] in done]
json.dump(merged, open('inventory/search-eval.json', 'w'), ensure_ascii=False, indent=1)
print('ИТОГО в search-eval.json:', len(merged), 'из', len(recs))
