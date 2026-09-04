# -*- coding: utf-8 -*-
"""Переснять указанные разделы с новой разметкой и заменить их записи в реестре."""
import json, os, sys, time
import concurrent.futures as cf
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from crawl_sections import fetch, parse, BASE, OUT

HERE = os.path.dirname(os.path.abspath(__file__))
kind = sys.argv[1] if len(sys.argv) > 1 else 'legacy'

inv = [json.loads(l) for l in open(OUT, encoding='utf-8') if l.strip()]
targets = [r['path'] for r in inv if r['article_kind'] == kind]
print('переснимаю %d разделов (article_kind=%s)' % (len(targets), kind), flush=True)


def one(p):
    st, s = fetch(BASE + p)
    time.sleep(0.4)
    if st != 200 or not s:
        return p, None
    r = parse(BASE + p, s)
    r['http'] = st
    return p, r


fresh = {}
with cf.ThreadPoolExecutor(max_workers=5) as ex:
    for p, r in ex.map(one, targets):
        if r:
            fresh[p] = r

n = 0
for i, r in enumerate(inv):
    f = fresh.get(r['path'])
    if f:
        f['is_duplicate'] = r.get('is_duplicate', False)
        f['canonical_target'] = r.get('canonical_target', '')
        inv[i] = f
        n += 1
with open(OUT, 'w', encoding='utf-8') as fo:
    for r in inv:
        fo.write(json.dumps(r, ensure_ascii=False) + '\n')
print('обновлено записей:', n)
for r in inv:
    if r['path'] in fresh and r['article_kind'] == kind:
        print('  %-60s знаков %5d  ссылок %3d' % (r['path'][:60], r['article_chars'], len(r['article_links'])))
