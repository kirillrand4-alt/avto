# -*- coding: utf-8 -*-
"""Второй проход: по проблемным страницам из check-published.jsonl выясняем,
ЧЕЙ текст на них реально лежит.

Строим индекс «H2-заголовок -> slug» по всем 759 опубликованным блокам
(publish/plain и gen-orig — чтобы отличить «стоит старая версия» от
«стоит текст чужой страницы»), затем перекачиваем проблемные URL и
сопоставляем найденные на странице H2.

Выход: diagnose-published.jsonl
"""
import json, os, re, sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from check_published import (DIR, HEADERS, TIMEOUT, norm, strip_tags, h1_of,
                             canonical_of)

JL = os.path.join(DIR, 'check-published.jsonl')
OUT = os.path.join(DIR, 'diagnose-published.jsonl')
PLAIN = os.path.join(DIR, 'publish', 'plain')
GEN_ORIG = os.path.join(DIR, 'gen-orig')
WORKERS = int(os.environ.get('CHECK_WORKERS', '6'))
BAD = {'TEXT_MISSING', 'TEXT_PARTIAL', 'REDIRECT_TEXT_MISSING',
       'REDIRECT_TEXT_PARTIAL', 'HTTP_ERROR', 'FETCH_FAIL', 'CRASH'}
H2RE = re.compile(r'<h2[^>]*>(.*?)</h2>', re.S | re.I)


def h2list(html):
    return [norm(strip_tags(x)) for x in H2RE.findall(html)]


def build_index():
    """H2 -> [(slug, версия)]. Версии: 'publish' (то, что отдавали в Битрикс)
    и 'orig' (бэкап до правок) — чтобы поймать «на сайте старая редакция»."""
    idx = {}
    for fn in os.listdir(PLAIN):
        if not fn.endswith('.html'):
            continue
        slug = fn[:-5]
        with open(os.path.join(PLAIN, fn), encoding='utf-8') as f:
            for h in h2list(f.read()):
                idx.setdefault(h, []).append((slug, 'publish'))
    if os.path.isdir(GEN_ORIG):
        for fn in os.listdir(GEN_ORIG):
            if not (fn.startswith('result-') and fn.endswith('.json')):
                continue
            slug = fn[len('result-'):-len('.json')]
            try:
                with open(os.path.join(GEN_ORIG, fn), encoding='utf-8') as f:
                    body = json.load(f).get('text_html', '')
            except Exception:
                continue
            for h in h2list(body):
                idx.setdefault(h, []).append((slug, 'orig'))
    return idx


def diagnose(rec, idx, session):
    url = rec.get('final_url') or rec['url']
    out = {'slug': rec['slug'], 'url': rec['url'], 'checked_url': url,
           'status_prev': rec.get('status')}
    try:
        r = session.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
    except Exception as e:
        out['error'] = repr(e)
        return out
    html = r.text
    heads = h2list(html)
    # служебные H2 шаблона (FAQ, «Ответы на часто задаваемые вопросы») не
    # различают страницы — считаем их неинформативными
    owners = {}
    for h in heads:
        for slug, ver in idx.get(h, []):
            owners.setdefault((slug, ver), []).append(h)
    ranked = sorted(owners.items(), key=lambda kv: -len(kv[1]))
    out.update({
        'http_status': r.status_code,
        'page_h2': heads,
        'page_h1': h1_of(html),
        'canonical': canonical_of(html),
        'has_byline': 'руспром' in norm(strip_tags(html)),
        'text_owner': [{'slug': s, 'version': v, 'matched_h2': len(hs)}
                       for (s, v), hs in ranked[:4]],
    })
    top = ranked[0] if ranked else None
    if not top:
        out['verdict'] = 'NO_KNOWN_TEXT'          # нашего текста нет вообще
    elif top[0][0] == rec['slug']:
        out['verdict'] = ('OWN_TEXT_OLD_VERSION' if top[0][1] == 'orig'
                          else 'OWN_TEXT_PARTIAL')
    else:
        out['verdict'] = 'FOREIGN_TEXT'           # лежит текст другой страницы
        out['foreign_slug'] = top[0][0]
    return out


def main():
    recs = [json.loads(l) for l in open(JL, encoding='utf-8') if l.strip()]
    recs = list({r['slug']: r for r in recs}.values())
    bad = [r for r in recs if r.get('status') in BAD]
    print(f'проблемных страниц: {len(bad)}', flush=True)
    idx = build_index()
    print(f'индекс H2: {len(idx)} заголовков', flush=True)

    done = set()
    if os.path.exists(OUT):
        with open(OUT, encoding='utf-8') as f:
            for line in f:
                try:
                    done.add(json.loads(line)['slug'])
                except Exception:
                    pass
    bad = [r for r in bad if r['slug'] not in done]

    session = requests.Session()
    with open(OUT, 'a', encoding='utf-8') as out, \
            ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futs = [pool.submit(diagnose, r, idx, session) for r in bad]
        for i, fut in enumerate(as_completed(futs), 1):
            out.write(json.dumps(fut.result(), ensure_ascii=False) + '\n')
            out.flush()
            if i % 20 == 0:
                print(f'  {i}/{len(bad)}', flush=True)
    print('готово', flush=True)


if __name__ == '__main__':
    main()
