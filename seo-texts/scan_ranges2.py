# -*- coding: utf-8 -*-
"""Финальный скан гибридных диапазонов: заявленный в прозе диапазон кВт на БРЕНДОВЫХ страницах
сверяется с ПОЛНЫМ составом каталога (выгрузка Битрикса, бренд × подтип).
Выход: range-mismatch-final.md + range-fix-queue.txt"""
import json, glob, os, re
from scan_ranges import claims

DIR = os.path.dirname(os.path.abspath(__file__))
REF = json.load(open(os.path.join(DIR, 'brand-power-sub.json')))


def norm(s):
    return re.sub(r'[^a-z0-9а-я]', '', (s or '').lower())


def subtype(slug, h1):
    t = (slug + ' ' + (h1 or '')).lower()
    if 'porshn' in t or 'поршн' in t: return 'porshn'
    if 'spiral' in t or 'спираль' in t: return 'spiral'
    if 'dizel' in t or 'дизель' in t: return 'dizel'
    if 'vint' in t or 'винт' in t: return 'vint'
    return 'all'


def main():
    rows = []; checked = 0; nobrand = 0
    for f in sorted(glob.glob(os.path.join(DIR, 'gen', 'result-*.json'))):
        slug = os.path.basename(f)[len('result-'):-len('.json')]
        try:
            d = json.load(open(f)); p = json.load(open(os.path.join(DIR, f'gen/payload-{slug}.json')))
        except Exception:
            continue
        if p.get('category') != 'compressor':
            continue                            # кВт-диапазоны в осушителях и т.п. не сверяем этим эталоном
        text = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', d.get('text_html', '')))
        cl = claims(text)
        if not cl:
            continue
        brand = p.get('page_brand')
        ref = REF.get(norm(brand)) if brand else None
        if not ref:
            nobrand += 1
            continue
        st = subtype(slug, p.get('h1'))
        rng = ref.get(st) or ref.get('all')
        if not rng or rng[2] < 3:               # <3 позиций - эталон ненадёжен
            continue
        rmin, rmax, n = rng
        checked += 1
        for x, y, quote in cl:
            probs = []
            if y > rmax * 1.2:
                probs.append(f'потолок {y:g} ЗАВЫШЕН (в каталоге до {rmax:g})')
            if y < rmax * 0.6 and re.search(r'диапазон|линейк|от\s', quote):
                probs.append(f'потолок {y:g} ЗАНИЖЕН (в каталоге до {rmax:g})')
            if x < rmin * 0.6:
                probs.append(f'пол {x:g} ниже каталога ({rmin:g})')
            if probs:
                rows.append((slug, quote, '; '.join(probs), f'{rmin:g}-{rmax:g} кВт (n={n}, {st})'))
    slugs = sorted(set(r[0] for r in rows))
    rep = ['# Гибридные диапазоны: проза vs ПОЛНЫЙ каталог (Битрикс, бренд × подтип)\n',
           f'Брендовых компрессорных страниц с заявленными диапазонами: {checked} | '
           f'страниц с расхождением: {len(slugs)} | claim-ов: {len(rows)}\n']
    for slug, q, why, real in rows:
        rep.append(f'- `{slug}`\n  «{q}» -> {why} | каталог: {real}')
    open(os.path.join(DIR, 'range-mismatch-final.md'), 'w', encoding='utf-8').write('\n'.join(rep))
    open(os.path.join(DIR, 'range-fix-queue.txt'), 'w').write('\n'.join(slugs) + '\n')
    print(f'проверено {checked} брендовых страниц | расхождения на {len(slugs)} страницах ({len(rows)} мест)')
    print('-> range-mismatch-final.md, range-fix-queue.txt')


if __name__ == '__main__':
    main()
