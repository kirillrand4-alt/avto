# -*- coding: utf-8 -*-
"""Проверка всех ссылок из статей на битые. Дедуп, параллельно, кэш в link-codes.json."""
import json, os, re, time, gzip, threading
import concurrent.futures as cf
import urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'link-codes.json')
BASE = 'https://prokompressor.ru'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36'


def code(link):
    u = link if link.startswith('http') else BASE + link
    if not u.startswith('http'):
        return -1
    for i in range(2):
        try:
            rq = urllib.request.Request(u, headers={'User-Agent': UA}, method='GET')
            with urllib.request.urlopen(rq, timeout=30) as r:
                r.read(2048)
                return r.status
        except urllib.error.HTTPError as e:
            return e.code
        except Exception:
            if i:
                return 0
            time.sleep(1.5)
    return 0


def main():
    inv = [json.loads(l) for l in open(os.path.join(HERE, 'inventory.jsonl'), encoding='utf-8') if l.strip()]
    links = set()
    for r in inv:
        for l in r['article_links']:
            l = l.split('#')[0]
            if l and not l.startswith(('tel:', 'mailto:', 'javascript:')):
                links.add(l)
    done = json.load(open(OUT)) if os.path.exists(OUT) else {}
    todo = sorted(links - set(done))
    print('ссылок всего %d, уникальных %d, проверить %d' % (
        sum(len(r['article_links']) for r in inv), len(links), len(todo)), flush=True)
    lock = threading.Lock()
    n = [0]

    def one(l):
        c = code(l)
        time.sleep(0.3)
        with lock:
            done[l] = c
            n[0] += 1
            if n[0] % 100 == 0:
                print('  %d/%d' % (n[0], len(todo)), flush=True)
        return c

    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(one, todo))
    json.dump(done, open(OUT, 'w'), ensure_ascii=False, indent=0)
    bad = {k: v for k, v in done.items() if v >= 400 or v == 0}
    print('ГОТОВО. Проверено %d, битых %d' % (len(done), len(bad)))
    for k, v in sorted(bad.items(), key=lambda x: -x[1])[:40]:
        print('  %s  %s' % (v, k))


if __name__ == '__main__':
    main()
