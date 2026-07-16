# -*- coding: utf-8 -*-
"""Механическая правка гибридных диапазонов «от X до Y кВт» на брендовых страницах:
подставляем истинные границы каталога из payload.power_range_catalog (Битрикс).
Только страницы из range-fix-queue.txt. Идемпотентно. Выход: patch-ranges-report.md"""
import json, os, re, sys

DIR = os.path.dirname(os.path.abspath(__file__))
DRY = '--dry' in sys.argv
KW = r'(\d+(?:[.,]\d+)?)'


def fmt(v):
    return f'{v:g}'.replace('.', ',')


def patch(html, lo, hi):
    """Заменить X/Y в конструкциях «от X до Y (+)? кВт» и «диапазон/мощност... X-Y кВт»."""
    out = []
    def sub_ot_do(m):
        return f'{m.group(1)}от {fmt(lo)} до {fmt(hi)} кВт'
    h2, n1 = re.subn(r'((?:диапазон[а-я]*|мощност[а-я]*|линейк[а-я]*)[^.<]{0,40}?)от\s*' + KW + r'\s*до\s*' + KW + r'\s*\+?\s*кВт',
                     sub_ot_do, html)
    def sub_dash(m):
        return f'{m.group(1)}{fmt(lo)}-{fmt(hi)} кВт'
    h3, n2 = re.subn(r'((?:диапазон[а-я]*|мощност[а-я]*)[^.<]{0,25}?)' + KW + r'\s*[-–]\s*' + KW + r'\s*\+?\s*кВт',
                     sub_dash, h2)
    return h3, n1 + n2


def main():
    slugs = [l.strip() for l in open(os.path.join(DIR, 'range-fix-queue.txt')) if l.strip()]
    rep = []; total = 0
    for slug in slugs:
        try:
            d = json.load(open(os.path.join(DIR, f'gen/result-{slug}.json')))
            p = json.load(open(os.path.join(DIR, f'gen/payload-{slug}.json')))
        except Exception as e:
            rep.append(f'- `{slug}` SKIP ({e!r})'); continue
        rng = p.get('power_range_catalog')
        if not rng:
            rep.append(f'- `{slug}` SKIP (нет power_range_catalog)'); continue
        h, n = patch(d['text_html'], rng['min_kvt'], rng['max_kvt'])
        if n and not DRY:
            d['text_html'] = h
            json.dump(d, open(os.path.join(DIR, f'gen/result-{slug}.json'), 'w'), ensure_ascii=False, indent=1)
        total += n
        rep.append(f'- `{slug}`: заменено {n} диапазон(а) -> {fmt(rng["min_kvt"])}-{fmt(rng["max_kvt"])} кВт ({rng["subtype"]})')
    open(os.path.join(DIR, 'patch-ranges-report.md'), 'w', encoding='utf-8').write(
        f'# Мех-правка диапазонов ({"DRY" if DRY else "APPLIED"})\n\n' + '\n'.join(rep))
    print(f'{"[DRY] " if DRY else ""}страниц: {len(slugs)} | замен: {total} -> patch-ranges-report.md')


if __name__ == '__main__':
    main()
