# -*- coding: utf-8 -*-
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from gen_provider import make_client, call

MISSING = {
 'filtry-magistralnye': 'Магистральные фильтры сжатого воздуха',
 'resivery': 'Ресиверы (воздухосборники) для компрессоров',
 'generatory-azota': 'Генераторы азота (адсорбционные/мембранные)',
}
PROMPT = open('enrich_categories.py').read().split('PROMPT = """')[1].split('"""')[0]
client = make_client()

def worker(kv):
    slug, cat = kv
    msg = call(client, [{'role':'user','content':PROMPT.format(cat=cat)}], 'claude-fable-5')
    text = ''.join(b.text for b in msg.content if b.type=='text').strip()
    open(f'kb/category-{slug}.md','w').write(text+'\n')
    print(f'ок: {cat[:40]}', flush=True)

with ThreadPoolExecutor(max_workers=3) as ex:
    futs={ex.submit(worker,kv):kv for kv in MISSING.items()}
    for f in as_completed(futs):
        try: f.result()
        except Exception as e: print(f'FAIL {futs[f][0]}: {repr(e)[:90]}', flush=True)
print('ДОСОБРАНО')
