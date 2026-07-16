# -*- coding: utf-8 -*-
"""Массовая генерация текстов через провайдерский API (Fable 5), параллельно и резюмируемо.

Тяжёлая работа (генерация + авто-доводка по QA) — на провайдерском токене, НЕ на сессии.
Общий клиент и proj_urls на все потоки. Пропускаем уже готовые result-*.json.
Отчёт: gen/_batch-report.jsonl (по строке на страницу) + сводка в конце.

Использование:
  python3 gen_batch.py --category ref_dryer            # одна категория
  python3 gen_batch.py --noncompressor                 # все некомпрессорные
  python3 gen_batch.py --all --workers 6               # всё
  python3 gen_batch.py --slugs file.txt                # список слугов из файла
  python3 gen_batch.py ... --limit 20                  # первые N (для контроля)
"""
import json, os, sys, time, glob, threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import gen_provider as gp

DIR = os.path.dirname(os.path.abspath(__file__))
GEN = os.path.join(DIR, 'gen')
REPORT = os.path.join(GEN, '_batch-report.jsonl')
NONCOMPRESSOR = {'ref_dryer', 'ads_dryer', 'dryer_other', 'receiver', 'filter', 'separator',
                 'n2_gen', 'o2_gen', 'air_prep', 'spare_parts', 'flowmeter', 'gas_other'}
_lock = threading.Lock()


def payload_slug(path):
    return os.path.basename(path)[len('payload-'):-len('.json')]


def select():
    args = sys.argv
    cat = noncompr = allf = None
    slugs_file = None; limit = None
    for i, a in enumerate(args):
        if a == '--category': cat = args[i + 1]
        if a == '--noncompressor': noncompr = True
        if a == '--all': allf = True
        if a == '--slugs': slugs_file = args[i + 1]
        if a == '--limit': limit = int(args[i + 1])
    items = []
    if slugs_file:
        want = set(l.strip() for l in open(slugs_file) if l.strip())
        for p in glob.glob(os.path.join(GEN, 'payload-*.json')):
            if payload_slug(p) in want:
                items.append(p)
    else:
        for p in glob.glob(os.path.join(GEN, 'payload-*.json')):
            d = json.load(open(p))
            c = d.get('category', 'compressor')
            if allf or (cat and c == cat) or (noncompr and c in NONCOMPRESSOR):
                items.append(p)
    items.sort()
    if limit is not None:
        items = items[:limit]      # --limit 0 -> пусто (сухой прогон), не «без лимита»
    return items


def worker(payload_path, client, proj_urls, model, price_known):
    slug = payload_slug(payload_path)
    out = os.path.join(GEN, f'result-{slug}.json')
    if os.path.exists(out):
        return {'slug': slug, 'status': 'skip'}
    try:
        r = gp.run_one(slug, payload_path=payload_path, out_path=out, model=model,
                       price_known=price_known, client=client, proj_urls=proj_urls)
        r['status'] = 'clean' if r['clean'] else 'issues'
        with _lock:
            with open(REPORT, 'a') as f:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
        return r
    except Exception as ex:
        err = {'slug': slug, 'status': 'error', 'error': repr(ex)[:200]}
        with _lock:
            with open(REPORT, 'a') as f:
                f.write(json.dumps(err, ensure_ascii=False) + '\n')
        return err


def main():
    workers = 6; model = 'claude-fable-5'; price_known = False
    for i, a in enumerate(sys.argv):
        if a == '--workers': workers = int(sys.argv[i + 1])
        if a == '--model': model = sys.argv[i + 1]
        if a == '--price': price_known = True
    items = select()
    todo = [p for p in items if not os.path.exists(os.path.join(GEN, f'result-{payload_slug(p)}.json'))]
    print(f'выбрано {len(items)}, к генерации {len(todo)} (остальные готовы), workers={workers}, model={model}',
          file=sys.stderr)
    if not todo:
        print('нечего генерировать — все готовы', file=sys.stderr); return

    client = gp.make_client()
    try:
        proj_urls = set(r['url'].replace('https://prokompressor.ru', '')
                        for r in json.load(open(os.path.join(DIR, 'projects-index.json'))) if not r.get('error'))
    except FileNotFoundError:
        proj_urls = None

    t0 = time.time(); done = {}; out_tok = 0; n = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(worker, p, client, proj_urls, model, price_known): p for p in todo}
        for f in as_completed(futs):
            r = f.result(); n += 1
            done[r['status']] = done.get(r['status'], 0) + 1
            out_tok += r.get('output_tokens', 0) or 0
            tag = {'clean': 'OK', 'issues': '~', 'error': 'ERR', 'skip': '.'}.get(r['status'], '?')
            iss = ''
            if r['status'] == 'issues':
                iss = ' | ' + '; '.join(r['rounds'][-1]['issues'])[:120]
            print(f'[{n}/{len(todo)}] {tag} {r["slug"]}{iss}', file=sys.stderr)
    dt = time.time() - t0
    print(f'\nИТОГ: {done} за {dt/60:.1f} мин | output-токенов ~{out_tok} '
          f'(~${out_tok/1e6*50:.2f} на output по Fable)', file=sys.stderr)


if __name__ == '__main__':
    main()
