# -*- coding: utf-8 -*-
"""Мех-скан «гибридных диапазонов»: заявленный в прозе диапазон мощностей (от X до Y кВт)
сверяется с реальными мощностями товаров ЭТОЙ ЖЕ страницы (products-index + sample_models).
Флагуем, когда потолок/пол заметно расходится с фактурой. Выход: range-mismatch.md"""
import json, glob, os, re

DIR = os.path.dirname(os.path.abspath(__file__))
IDX = json.load(open(os.path.join(DIR, 'products-index.json')))
try:
    BXPOW = json.load(open(os.path.join(DIR, 'bitrix-power.json')))   # имя/КОД-url -> кВт (из выгрузки)
except FileNotFoundError:
    BXPOW = {}

KW = r'(\d+(?:[.,]\d+)?)'
# заявленные диапазоны в прозе: «от X до Y кВт», «X до Y кВт», «X-Y кВт» с окружением «диапазон/мощност/линейк/серия/от»
CLAIM_RES = [
    re.compile(r'(?:диапазон[а-я]*|мощност[а-я]*|линейк[а-я]*)[^.<]{0,40}?от\s*' + KW + r'\s*до\s*' + KW + r'\s*\+?\s*кВт'),
    re.compile(r'от\s*' + KW + r'\s*до\s*' + KW + r'\s*\+?\s*кВт'),
    re.compile(r'(?:диапазон[а-я]*|мощност[а-я]*)[^.<]{0,25}?' + KW + r'\s*[-–]\s*' + KW + r'\s*\+?\s*кВт'),
]
PLUS_RE = re.compile(KW + r'\s*\+\s*кВт')


def page_powers(slug, payload):
    """Реальные кВт со страницы: сперва структурная мощность из выгрузки Битрикса
    (матч по URL товара и по имени), затем «N кВт» в имени как запасной путь."""
    items = [it for it in (IDX.get(slug) or []) if isinstance(it, dict)]
    names = [it['name'] for it in items if it.get('name')] + (payload.get('sample_models') or [])
    pw = []
    for it in items:                       # по URL (IE_CODE) - самый надёжный матч
        u = (it.get('url') or '')
        if u in BXPOW:
            pw.append(BXPOW[u])
    for n in names:                        # по точному имени из выгрузки
        if n in BXPOW:
            pw.append(BXPOW[n])
        for m in re.finditer(KW + r'\s*кВт', n):   # запасной путь: кВт прямо в имени
            pw.append(float(m.group(1).replace(',', '.')))
    return sorted(set(pw))


def claims(text):
    out = []
    for cre in CLAIM_RES:
        for m in cre.finditer(text):
            x, y = float(m.group(1).replace(',', '.')), float(m.group(2).replace(',', '.'))
            if 0.1 <= x < y <= 2000:            # правдоподобный диапазон мощностей
                out.append((x, y, m.group(0)[:90]))
    # дедуп по (x,y)
    seen = set(); ded = []
    for x, y, s in out:
        if (x, y) not in seen:
            seen.add((x, y)); ded.append((x, y, s))
    return ded


def main():
    rows = []
    for f in sorted(glob.glob(os.path.join(DIR, 'gen', 'result-*.json'))):
        slug = os.path.basename(f)[len('result-'):-len('.json')]
        try:
            d = json.load(open(f)); p = json.load(open(os.path.join(DIR, f'gen/payload-{slug}.json')))
        except Exception:
            continue
        text = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', d.get('text_html', '')))
        cl = claims(text)
        if not cl:
            continue
        pw = page_powers(slug, p)
        if len(pw) < 2:                          # мало фактуры - сверять не с чем
            continue
        rmin, rmax = pw[0], pw[-1]
        for x, y, quote in cl:
            # потолок завышен (>30% над реальным max) или занижен (<70% реального max);
            # пол ниже реального min более чем на 30%
            hi_off = y > rmax * 1.3
            hi_under = y < rmax * 0.7
            lo_off = x < rmin * 0.7
            if hi_off or hi_under or lo_off:
                why = []
                if hi_off: why.append(f'потолок {y:g} завышен (реально до {rmax:g})')
                if hi_under: why.append(f'потолок {y:g} занижен (реально до {rmax:g})')
                if lo_off: why.append(f'пол {x:g} ниже реального ({rmin:g})')
                rows.append((slug, quote, '; '.join(why), f'{rmin:g}-{rmax:g}'))
    rep = ['# Гибридные диапазоны мощностей (заявлено в прозе vs товары страницы)\n',
           f'Проверено страниц с заявленными диапазонами и фактурой: см. ниже. Несовпадений: {len(rows)}\n']
    for slug, q, why, real in rows:
        rep.append(f'- `{slug}`\n  заявлено: «{q}» | {why} | реально на странице: {real} кВт')
    open(os.path.join(DIR, 'range-mismatch.md'), 'w', encoding='utf-8').write('\n'.join(rep))
    print(f'несовпадений: {len(rows)} -> range-mismatch.md')
    for slug, q, why, real in rows[:25]:
        print(f'  {slug} | «{q[:60]}» | {why} | реал {real}')


if __name__ == '__main__':
    main()
