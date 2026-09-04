# -*- coding: utf-8 -*-
"""Замыкание реестра: обойти ссылки со всех известных разделов и добрать то,
что ещё не в реестре. Повторять волнами, пока не перестанут находиться новые.
Кандидаты глубины 1 фильтруются по page_kind (товары отбрасываются).
"""
import json, os, re, sys, time
import concurrent.futures as cf
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from crawl_sections import fetch, parse, links_of, BASE, OUT

HERE = os.path.dirname(os.path.abspath(__file__))


def load():
    return {json.loads(l)['path'] for l in open(OUT, encoding='utf-8') if l.strip()}


def main():
    have = load()
    print('в реестре:', len(have), flush=True)
    seeds = sorted(have)
    fout = open(OUT, 'a', encoding='utf-8')
    ferr = open(os.path.join(HERE, 'crawl-errors.log'), 'a', encoding='utf-8')

    def scan(p):
        st, s = fetch(BASE + p)
        time.sleep(0.35)
        return links_of(s) if st == 200 and s else set()

    wave = 0
    while True:
        wave += 1
        found = set()
        with cf.ThreadPoolExecutor(max_workers=6) as ex:
            for got in ex.map(scan, seeds):
                found |= got
        new = sorted({l for l in found if l.startswith('/catalog/') and l.endswith('/')} - have)
        print('волна %d: просканировано %d, новых кандидатов %d' % (wave, len(seeds), len(new)), flush=True)
        if not new:
            break

        def one(p):
            st, s = fetch(BASE + p)
            time.sleep(0.35)
            if st != 200 or not s:
                return p, None, st
            r = parse(BASE + p, s)
            r['http'] = st
            return p, r, st

        added = []
        with cf.ThreadPoolExecutor(max_workers=6) as ex:
            for p, r, st in ex.map(one, new):
                have.add(p)
                if r is None:
                    ferr.write('%s\t%s%s\n' % (st, BASE, p))
                    continue
                if r['page_kind'] == 'product':
                    continue
                fout.write(json.dumps(r, ensure_ascii=False) + '\n')
                fout.flush()
                added.append(p)
                print('  + %-16s %s' % (r['page_kind'], p), flush=True)
        print('  добавлено разделов: %d' % len(added), flush=True)
        if not added:
            break
        seeds = added
    fout.close(); ferr.close()
    print('ЗАМКНУТО. Разделов в реестре:', len(load()))


if __name__ == '__main__':
    main()
