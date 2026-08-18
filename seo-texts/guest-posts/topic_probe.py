#!/usr/bin/env python3
"""Реальная тематика площадки: заголовки и разделы, а не ярлык биржи.

Владелец 05.08: «тематике особо не верь у доноров». В FINAL-DONORS-VERIFIED
я всё равно разложил доноров по колонке «Тематика» из выгрузки Miralinks -
её проставляет вебмастер, биржа не проверяет. Этот скрипт снимает главную,
берёт разделы меню и заголовки материалов, чтобы классификацию делал текст
самой площадки.
"""
import concurrent.futures as cf
import json, os, re, sys
import httpx

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36')
TAG, WS = re.compile(r'<[^>]+>'), re.compile(r'\s+')
SKIP = re.compile(r'(?i)(войти|регистр|подписк|контакт|поиск|политик|соглашен|карта сайта|rss)')


def probe(domain):
    try:
        c = httpx.Client(follow_redirects=True, timeout=25, verify=False,
                         headers={'user-agent': UA})
        r = c.get(f'https://{domain}/')
        html = r.text
    except Exception as e:                                   # noqa: BLE001
        return {'domain': domain, 'error': repr(e)[:120]}
    html = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', html)
    title = re.search(r'(?is)<title[^>]*>(.*?)</title>', html)
    desc = re.search(r'(?is)<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']', html)
    pairs = [(h, WS.sub(' ', TAG.sub(' ', a)).strip())
             for h, a in re.findall(r'(?is)<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html)]
    nav, heads, seen = [], [], set()
    for href, txt in pairs:
        if 25 <= len(txt) <= 140:
            heads.append(txt)
        if not (2 <= len(txt) <= 22) or SKIP.search(txt):
            continue
        if href.startswith(('#', 'mailto:', 'tel:', 'javascript:')):
            continue
        full = href if href.startswith('http') else f'https://{domain}/' + href.lstrip('/')
        if domain not in full or full.rstrip('/') in seen:
            continue
        seen.add(full.rstrip('/'))
        nav.append({'text': txt, 'url': full})
    return {'domain': domain, 'http': r.status_code,
            'title': WS.sub(' ', TAG.sub('', title.group(1))).strip() if title else '',
            'description': (desc.group(1)[:250] if desc else ''),
            'sections': nav[:35],
            'headlines': list(dict.fromkeys(heads))[:40]}


def main():
    doms = [l.strip() for l in open(sys.argv[1], encoding='utf-8') if l.strip()]
    out = {}
    with cf.ThreadPoolExecutor(max_workers=10) as ex:
        for d in ex.map(probe, doms):
            out[d['domain']] = d
            print(f"  {d['domain']:26} {d.get('title','')[:60]}", flush=True)
    json.dump(out, open('topic-raw.json', 'w'), ensure_ascii=False, indent=1)
    print(f'снято: {len(out)}')





# ── фаза 2: заглянуть В РАЗДЕЛЫ ────────────────────────────────────────────────
# Владелец 18.08: «там ещё могут быть разные разделы, может раздел подходящий
# будет». Это и есть правило проекта: размещение ложится в РАЗДЕЛ, поэтому
# площадка «не нашей тематики» с живым разделом «Промышленность» нам подходит,
# а «промышленный» портал без такого раздела - нет.
SECT_HINT = re.compile(r'(?i)(промышленн|производств|бизнес|эконом|строит|ремонт|'
                       r'технолог|оборудован|энерг|агро|сельск|авто|транспорт|логист|'
                       r'новости компан|пресс|партнёр|партнер|наука|техник)')


def probe_sections(rec, limit=8):
    """Заголовки материалов внутри подходящих по названию разделов."""
    out = []
    cand = [s for s in rec.get('sections', []) if SECT_HINT.search(s['text'])][:limit]
    if not cand:
        cand = rec.get('sections', [])[:4]
    for s in cand:
        try:
            c = httpx.Client(follow_redirects=True, timeout=20, verify=False,
                             headers={'user-agent': UA})
            html = c.get(s['url']).text
        except Exception:                                    # noqa: BLE001
            continue
        html = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', html)
        heads = [WS.sub(' ', TAG.sub(' ', m)).strip()
                 for m in re.findall(r'(?is)<a[^>]*>(.*?)</a>', html)]
        heads = [h for h in dict.fromkeys(heads) if 25 <= len(h) <= 140][:18]
        if heads:
            out.append({'section': s['text'], 'url': s['url'], 'headlines': heads})
    return out


def phase2():
    data = json.load(open('topic-raw.json', encoding='utf-8'))
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        for dom, sect in zip(data, ex.map(lambda d: probe_sections(data[d]), data)):
            data[dom]['section_pages'] = sect
            print(f'  {dom:26} разделов снято {len(sect)}', flush=True)
    json.dump(data, open('topic-raw.json', 'w'), ensure_ascii=False, indent=1)


if __name__ == '__main__':
    if '--sections' in sys.argv:
        phase2()
    else:
        main()
