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
    anchors = [WS.sub(' ', TAG.sub(' ', m)).strip()
               for m in re.findall(r'(?is)<a[^>]*>(.*?)</a>', html)]
    nav = [a for a in anchors if 2 <= len(a) <= 22 and not SKIP.search(a)]
    heads = [a for a in anchors if 25 <= len(a) <= 140]
    return {'domain': domain, 'http': r.status_code,
            'title': WS.sub(' ', TAG.sub('', title.group(1))).strip() if title else '',
            'description': (desc.group(1)[:250] if desc else ''),
            'sections': list(dict.fromkeys(nav))[:35],
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


if __name__ == '__main__':
    main()
