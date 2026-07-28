# -*- coding: utf-8 -*-
"""Проверка, что сгенерированные тексты реально встали на страницы prokompressor.ru.

Для каждой из 759 строк publish/manifest.csv:
  * запрос по URL из манифеста с отслеживанием цепочки редиректов;
  * фиксируем финальный URL, HTTP-статус, canonical, H1;
  * ищем на финальной странице 3 маркера-предложения из publish/plain/<slug>.html.

Выход: check-published.jsonl (по строке на страницу, резюмируемо — уже
пройденные slug пропускаются) + печать сводки. Сырой HTML не сохраняем.
"""
import csv, json, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

DIR = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(DIR, 'publish', 'manifest.csv')
PLAIN = os.path.join(DIR, 'publish', 'plain')
OUT = os.path.join(DIR, 'check-published.jsonl')

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120 Safari/537.36')
HEADERS = {
    'User-Agent': UA,
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'ru-RU,ru;q=0.9',
}
WORKERS = int(os.environ.get('CHECK_WORKERS', '6'))
TIMEOUT = 45

TAGS = re.compile(r'<(script|style|noscript)\b.*?</\1>', re.S | re.I)
ANYTAG = re.compile(r'<[^>]+>')
ENT = re.compile(r'&(?:nbsp|laquo|raquo|mdash|ndash|quot|amp|lt|gt|#\d+|#x[0-9a-f]+);', re.I)


def strip_tags(html):
    return ANYTAG.sub(' ', TAGS.sub(' ', html))


def norm(s):
    """Нормализация для сравнения: регистр, ё, кавычки, тире, пробелы, сущности."""
    s = ENT.sub(' ', s.replace('\xa0', ' '))
    s = s.lower().replace('ё', 'е')
    s = re.sub(r'[«»“”„‟\'"`]', '"', s)
    s = re.sub(r'[‐-―−-]', '-', s)
    return re.sub(r'\s+', ' ', s).strip()


def markers(slug):
    """3 предложения-маркера из опубликованного текстового блока."""
    path = os.path.join(PLAIN, slug + '.html')
    if not os.path.exists(path):
        return None, []
    with open(path, encoding='utf-8') as f:
        raw = f.read()
    h2 = re.search(r'<h2[^>]*>(.*?)</h2>', raw, re.S | re.I)
    head = norm(strip_tags(h2.group(1))) if h2 else None
    body = norm(strip_tags(raw))
    # предложения средней длины — они устойчивее коротких к случайным совпадениям
    sents = [x.strip() for x in re.split(r'(?<=[.!?]) ', body) if 60 <= len(x.strip()) <= 220]
    if not sents:
        sents = [body[i:i + 120] for i in range(0, min(len(body), 600), 200)]
    picks = []
    for frac in (0.15, 0.5, 0.85):
        i = min(len(sents) - 1, int(len(sents) * frac))
        if sents[i] not in picks:
            picks.append(sents[i])
    return head, picks


def canonical_of(html):
    m = re.search(r'<link[^>]+rel=["\']canonical["\'][^>]*>', html, re.I)
    if not m:
        return None
    h = re.search(r'href=["\']([^"\']+)["\']', m.group(0), re.I)
    return h.group(1) if h else None


def h1_of(html):
    m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S | re.I)
    return re.sub(r'\s+', ' ', strip_tags(m.group(1))).strip() if m else None


def classify(rec):
    if rec['http_status'] != 200:
        return 'HTTP_ERROR'
    hit = rec['markers_found']
    total = rec['markers_total']
    text_ok = total and hit == total
    text_partial = total and 0 < hit < total
    if rec['redirected']:
        if text_ok:
            return 'REDIRECT_TEXT_OK'
        return 'REDIRECT_TEXT_PARTIAL' if text_partial else 'REDIRECT_TEXT_MISSING'
    if text_ok:
        return 'OK'
    return 'TEXT_PARTIAL' if text_partial else 'TEXT_MISSING'


def check(row, session):
    slug, url = row['slug'], row['url']
    head, picks = markers(slug)
    rec = {'slug': slug, 'url': url, 'h1_expected': row.get('h1', ''),
           'markers_total': len(picks)}
    last_err = None
    for attempt in range(3):
        try:
            r = session.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
            break
        except Exception as e:  # сеть/таймаут — короткий бэкофф и ещё попытка
            last_err = repr(e)
            time.sleep(2 * (attempt + 1))
    else:
        rec.update({'http_status': 0, 'final_url': None, 'redirected': None,
                    'chain': [], 'markers_found': 0, 'error': last_err,
                    'status': 'FETCH_FAIL'})
        return rec

    html = r.text
    page = norm(strip_tags(html))
    found = [p for p in picks if p in page]
    chain = [{'from': h.url, 'status': h.status_code,
              'to': h.headers.get('Location')} for h in r.history]
    rec.update({
        'http_status': r.status_code,
        'final_url': r.url,
        'redirected': r.url.rstrip('/') != url.rstrip('/'),
        'chain': chain,
        'canonical': canonical_of(html),
        'h1_actual': h1_of(html),
        'h2_expected': head,
        'h2_found': bool(head) and head in page,
        'markers_found': len(found),
        'markers_missing': [p[:80] for p in picks if p not in found],
        'bytes': len(html),
    })
    rec['status'] = classify(rec)
    return rec


def main():
    with open(MANIFEST, encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f, delimiter=';'))
    done = set()
    if os.path.exists(OUT):
        with open(OUT, encoding='utf-8') as f:
            for line in f:
                try:
                    done.add(json.loads(line)['slug'])
                except Exception:
                    pass
    todo = [r for r in rows if r['slug'] not in done]
    print(f'всего {len(rows)}, уже проверено {len(done)}, к проверке {len(todo)}', flush=True)

    session = requests.Session()
    n = 0
    with open(OUT, 'a', encoding='utf-8') as out, \
            ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futs = {pool.submit(check, r, session): r['slug'] for r in todo}
        for fut in as_completed(futs):
            try:
                rec = fut.result()
            except Exception as e:
                rec = {'slug': futs[fut], 'status': 'CRASH', 'error': repr(e)}
            out.write(json.dumps(rec, ensure_ascii=False) + '\n')
            out.flush()
            n += 1
            if n % 25 == 0:
                print(f'  {n}/{len(todo)}', flush=True)
    print('готово', flush=True)


if __name__ == '__main__':
    main()
