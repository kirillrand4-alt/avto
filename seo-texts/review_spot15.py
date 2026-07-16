# -*- coding: utf-8 -*-
"""Спот-чек 15 топ-трафиковых страниц (по SEO-выгрузке) всей батареей ревьюеров."""
import json, os
from concurrent.futures import ThreadPoolExecutor, as_completed
import gen_provider as gp
from review_all_50 import readable, BATCH_NOTE, PERSONAS

DIR = os.path.dirname(os.path.abspath(__file__))

def one(pn, persona, bi, slugs, client):
    corpus = '\n\n'.join(readable(s) for s in slugs)
    note = BATCH_NOTE.replace('10 текстов', f'{len(slugs)} текстов').replace('10 ТЕКСТОВ', f'{len(slugs)} ТЕКСТОВ')
    try:
        msg = gp.call(client, [{'role': 'user', 'content': persona + note + corpus}], model='claude-fable-5')
        return pn, bi, ''.join(b.text for b in msg.content if b.type == 'text').strip()
    except Exception as e:
        return pn, bi, f'[пачка не удалась: {e!r}]'

def main():
    slugs = [l.strip() for l in open(os.path.join(DIR, 'spot15.txt')) if l.strip()]
    batches = [slugs[:8], slugs[8:]]
    client = gp.make_client()
    tasks = [(pn, p, bi, b) for (pn, p) in PERSONAS for bi, b in enumerate(batches, 1)]
    res = {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(one, pn, p, bi, b, client): (pn, bi) for pn, p, bi, b in tasks}
        for f in as_completed(futs):
            pn, bi, out = f.result(); res[(pn, bi)] = out
            print(f'готово: {pn} {bi}/2', flush=True)
    lines = ['# Спот-чек: 15 топ-трафиковых страниц (по SEO-выгрузке 01.01-15.07)\n']
    for pn, _ in PERSONAS:
        lines.append(f'\n\n# {pn}\n')
        for bi in (1, 2):
            lines.append(f'\n## Пачка {bi}\n\n{res.get((pn, bi), "-")}')
    open(os.path.join(DIR, 'review-spot15.md'), 'w', encoding='utf-8').write('\n'.join(lines))
    print('=> review-spot15.md')

if __name__ == '__main__':
    main()
