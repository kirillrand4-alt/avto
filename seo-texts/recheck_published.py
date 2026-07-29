# -*- coding: utf-8 -*-
"""Повторный обход только тех страниц, что были в check-published-todo.csv.

Проверяет, встал ли текст после переливки. Логика проверки та же, что в
check_published.py (3 предложения-маркера из publish/plain/<slug>.html).
Файл результата перезаписывается при каждом запуске — это срез «на сейчас».

Выход: recheck-published.jsonl + сравнение с прошлым прогоном.
"""
import csv, json, os, sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from check_published import DIR, MANIFEST, check

TODO = os.path.join(DIR, 'check-published-todo.csv')
PREV = os.path.join(DIR, 'check-published.jsonl')
OUT = os.path.join(DIR, 'recheck-published.jsonl')
WORKERS = int(os.environ.get('CHECK_WORKERS', '10'))


def main():
    with open(TODO, encoding='utf-8-sig') as f:
        want = {r['slug'] for r in csv.DictReader(f, delimiter=';')}
    with open(MANIFEST, encoding='utf-8-sig') as f:
        rows = [r for r in csv.DictReader(f, delimiter=';') if r['slug'] in want]
    print(f'к перепроверке: {len(rows)}', flush=True)

    session = requests.Session()
    recs = []
    with open(OUT, 'w', encoding='utf-8') as out, \
            ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futs = {pool.submit(check, r, session): r['slug'] for r in rows}
        for i, fut in enumerate(as_completed(futs), 1):
            try:
                rec = fut.result()
            except Exception as e:
                rec = {'slug': futs[fut], 'status': 'CRASH', 'error': repr(e)}
            recs.append(rec)
            out.write(json.dumps(rec, ensure_ascii=False) + '\n')
            out.flush()
            if i % 50 == 0:
                print(f'  {i}/{len(rows)}', flush=True)

    prev = {}
    if os.path.exists(PREV):
        with open(PREV, encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    r = json.loads(line)
                    prev[r['slug']] = r.get('status')

    fixed = [r for r in recs if r.get('status') == 'OK']
    still = [r for r in recs if r.get('status') != 'OK']
    print(f'\nвстало: {len(fixed)}   всё ещё нет: {len(still)}')
    if still:
        print('\nне встали:')
        for r in sorted(still, key=lambda x: x['slug']):
            print(f"  {r.get('status'):24} {r['slug']}")
            print(f"      {r['url']}")
            if r.get('redirected'):
                print(f"      -> {r.get('final_url')}")


if __name__ == '__main__':
    main()
