# -*- coding: utf-8 -*-
"""Добор разделов, которые не попали в обход.

Источники кандидатов:
  1) предки уже известных разделов (точный, без запросов к сайту);
  2) верхнеуровневое меню каталога - ловит разделы без подразделов
     (например /catalog/rekuperatory-tepla/), которых в предках быть не может.
Каждый кандидат скачивается и классифицируется по page_kind.
"""
import json, os, re, sys, time
import concurrent.futures as cf
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from crawl_sections import fetch, parse, page_kind, BASE, OUT

HERE = os.path.dirname(os.path.abspath(__file__))


def menu_candidates():
    """Ссылки на разделы из шапки/меню каталога."""
    st, s = fetch(BASE + '/catalog/')
    if st != 200:
        return set()
    cands = set()
    # меню разделов Aspro: menu-navigation__sections-item-link и обычные пункты меню
    for m in re.finditer(r'class="[^"]*(?:menu-navigation__sections-item-link|menu__link|'
                         r'sections-list__link|catalog-section-list)[^"]*"[^>]*href="'
                         r'(?:https://prokompressor\.ru)?(/catalog/[^"#?]*?/)"', s):
        cands.add(m.group(1))
    # запасной вариант: все ссылки глубины 1 со страницы каталога
    for m in re.finditer(r'href="(?:https://prokompressor\.ru)?(/catalog/[^"#?/]+/)"', s):
        cands.add(m.group(1))
    return cands


def main():
    have = set()
    for line in open(OUT, encoding='utf-8'):
        if line.strip():
            have.add(json.loads(line)['path'])

    cands = set(json.load(open(os.path.join(HERE, '_missing_ancestors.json'))))
    cands |= menu_candidates()
    todo = sorted(cands - have)
    print('кандидатов на добор: %d' % len(todo), flush=True)

    fout = open(OUT, 'a', encoding='utf-8')
    added = {'section': 0, 'section_landing': 0, 'product': 0, 'err': 0}

    def one(p):
        st, s = fetch(BASE + p)
        time.sleep(0.4)
        if st != 200 or not s:
            return p, None, st
        rec = parse(BASE + p, s)
        rec['http'] = st
        return p, rec, st

    with cf.ThreadPoolExecutor(max_workers=5) as ex:
        for p, rec, st in ex.map(one, todo):
            if rec is None:
                added['err'] += 1
                print('  %s %s' % (st, p))
                continue
            k = rec['page_kind']
            added[k] += 1
            print('  %-16s %s  h1=%s' % (k, p, rec['h1'][:45]))
            if k != 'product':
                fout.write(json.dumps(rec, ensure_ascii=False) + '\n')
    fout.close()
    print('ИТОГО:', added)


if __name__ == '__main__':
    main()
