# -*- coding: utf-8 -*-
"""Оценка релевантности поисковой выдачи через Fable API, параллельно."""
import json, re
from concurrent.futures import ThreadPoolExecutor, as_completed

from gen_provider import make_client, call

recs = [json.loads(l) for l in open('inventory/search-results.jsonl')]

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

def worker(idx_batch):
    idx, batch = idx_batch
    payload = [{'phrase': r['phrase'], 'found': r.get('found', 0),
                'top': [t['name'] for t in r.get('top', [])][:8]} for r in batch]
    prompt = PROMPT.format(batch=json.dumps(payload, ensure_ascii=False))
    msg = call(client, [{'role': 'user', 'content': prompt}], 'claude-fable-5')
    text = ''.join(b.text for b in msg.content if b.type == 'text')
    m = re.search(r'\[.*\]', text, re.S)
    arr = json.loads(m.group(0))
    print(f'батч {idx+1}: оценено {len(arr)}', flush=True)
    return arr

B = 15
batches = [recs[i:i+B] for i in range(0, len(recs), B)]
results = [None]*len(batches)
with ThreadPoolExecutor(max_workers=8) as ex:
    futs = {ex.submit(worker, (i, b)): i for i, b in enumerate(batches)}
    for f in as_completed(futs):
        try: results[futs[f]] = f.result()
        except Exception as e: print(f'батч {futs[f]+1} FAIL: {repr(e)[:120]}', flush=True)

flat = [x for r in results if r for x in r]
json.dump(flat, open('inventory/search-eval.json','w'), ensure_ascii=False, indent=1)
print('ИТОГО оценено:', len(flat))
