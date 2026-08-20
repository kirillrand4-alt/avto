#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Разбор Brands_spec_match_*.zip -> таблица «бренд → серия → кВт → бар → цена».

    python3 parse_spec.py <папка с *_spec_review.xlsx> [--out series.json]

Зачем: тир и ведущий вопрос страницы нельзя ставить на глаз, а инвентаризовать
сайты краулером долго. Спек-матч уже содержит нашу цену, цены шести конкурентов,
мощность и давление по каждой позиции - это готовый payload.

Серию вытаскиваем эвристикой: снимаем тип изделия и имя бренда, дальше первый
буквенный токен и есть серия. Мощность и давление разбираем по спискам реальных
значений, а не «первое число», иначе 270 из «SPINN 11-10-270» уедет в мощность.
"""
import argparse, collections, glob, json, os, re, statistics, sys

import openpyxl

KW = [2, 2.2, 3, 4, 5.5, 7.5, 11, 15, 18.5, 22, 30, 37, 45, 55, 75, 90, 110,
      132, 160, 185, 200, 220, 250, 280, 315, 355, 400, 450, 500]
BAR = [7, 7.5, 8, 10, 12, 13, 14, 15, 16, 20, 25, 30, 40]

# Описательные слова русского названия. Снимаем их все, в любом порядке и сколько
# бы их ни было: «Двухступенчатый винтовой компрессор низкого давления Dali ...».
DESCR = (r'двухступенчат|одноступенчат|винтов|поршнев|спиральн|центробежн|'
         r'дизельн|бензинов|электрическ|передвижн|мобильн|стационарн|'
         r'безмаслян|маслозаполненн|компрессор|установк|станци|блок|'
         r'низкого|высокого|среднего|давлени|воздушн|дожимн|бустер')
DESCR_RE = re.compile(r'(?i)\b(?:' + DESCR + r')\w*\b', re.U)
NOISE = re.compile(r'(?i)\b(бар|кВт|л|В|Гц|ф|new|нов\w*|IP\d+|шт|атм)\b\.?')

# Имя бренда в карточке не всегда совпадает с именем файла.
ALIAS = {
    'atlas':   ['atlas copco', 'copco', 'atlas'],
    'cross':   ['cross air', 'crossair', 'cross'],
    'zif':     ['зиф', 'zif'],
    'ekomak':  ['ekomak', 'екомак', 'еко'],
    'aso':     ['бежецк', 'бежецкий завод асо', 'асо', 'aso'],
    'chkz':    ['чкз', 'челябинский компрессорный завод', 'chkz'],
    'mmz':     ['ммз', 'mmz'],
}


def clean(name, brand):
    s = str(name or '').strip()
    for alias in ALIAS.get(brand.lower(), [brand]):
        s = re.sub(r'(?i)\b' + re.escape(alias) + r'\b', ' ', s)
    s = DESCR_RE.sub(' ', s)
    return re.sub(r'\s+', ' ', s).strip(' -,«»"')


def series_of(rest):
    """Первый буквенный токен = серия. ВК-7.5 -> ВК, SPINN 11-10 -> SPINN.

    Токен обрываем на первой цифре: в «VEGA201» и «DL16» число - это уже
    типоразмер, а не часть имени серии, и склеивать их нельзя, иначе одна серия
    рассыпается на два десятка мнимых.
    """
    m = re.match(r'(?i)([A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё\-‑]{0,14})', rest)
    if not m:
        return None
    s = re.split(r'\d', m.group(1))[0].strip('-').upper()
    return s if len(s) >= 2 else None


def nearest(val, allowed, tol=0.06):
    for a in allowed:
        if abs(val - a) <= max(tol, a * tol):
            return a
    return None


def parse_specs(rest):
    """Вернуть (кВт, бар). Числа сначала чистим от заведомого мусора."""
    txt = NOISE.sub(' ', rest)
    nums = [float(x.replace(',', '.')) for x in re.findall(r'\d+(?:[.,]\d+)?', txt)]
    kw = next((nearest(n, KW) for n in nums if nearest(n, KW)), None)
    # давление ищем среди чисел ПОСЛЕ мощности - в маркировке порядок «мощность/давление»
    tail = nums[nums.index(kw) + 1:] if kw in nums else nums
    bar = next((nearest(n, BAR) for n in tail if nearest(n, BAR)), None)
    if bar is None:
        bar = next((nearest(n, BAR) for n in nums if nearest(n, BAR)), None)
    return kw, bar


def money(v):
    if v is None:
        return None
    s = str(v).replace('\xa0', '').replace(' ', '').replace(',', '.')
    if not re.fullmatch(r'\d+(?:\.\d+)?', s):
        return None
    f = float(s)
    return f if 1000 <= f <= 500_000_000 else None


def read_brand(path):
    brand = os.path.basename(path).split('_')[0]
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    out = []
    for ws in wb.worksheets:
        hdr = None
        for row in ws.iter_rows(values_only=True):
            if hdr is None:
                hdr = [str(c or '').strip() for c in row]
                continue
            d = dict(zip(hdr, row))
            name = d.get('Наш товар') or d.get('Модель (у конкурентов, нас нет)')
            if not name:
                continue
            rest = clean(name, brand)
            ser = d.get('Серия') or series_of(rest)
            kw, bar = parse_specs(rest)
            if d.get('кВт'):
                kw = money(d['кВт']) or kw
            ours = money(d.get('Ваша цена'))
            comp = [money(d[k]) for k in hdr if k.endswith('.ru') and d.get(k)]
            comp = [c for c in comp if c]
            # Решение владельца 20.08: где своей цены нет, берём конкурентскую -
            # цену мы всё равно ставим такую же. Медиана, а не минимум: разброс
            # между сайтами тесный (медиана 1,05x), и минимум систематически
            # занижал бы на несколько процентов, то есть тоже был бы неверен.
            price, src = (ours, 'наша') if ours else \
                         ((statistics.median(comp), 'конкуренты') if comp else (None, None))
            out.append(dict(brand=brand, series=(str(ser).upper() if ser else None),
                            kw=kw, bar=bar, price=price, price_src=src,
                            comp_n=len(comp), name=str(name)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('--out', default='series.json')
    ap.add_argument('--only', help='список брендов через запятую')
    a = ap.parse_args()

    files = sorted(glob.glob(os.path.join(a.src, '*_spec_review.xlsx')))
    if a.only:
        keep = {x.strip().lower() for x in a.only.split(',')}
        files = [f for f in files
                 if os.path.basename(f).split('_')[0].lower() in keep]
    if not files:
        sys.exit('не найдено ни одного *_spec_review.xlsx')

    rows = []
    for f in files:
        try:
            rows += read_brand(f)
        except Exception as e:                      # битый файл не должен ронять прогон
            print(f'  ! {os.path.basename(f)}: {e}', file=sys.stderr)

    agg = collections.defaultdict(list)
    for r in rows:
        if r['series']:
            agg[(r['brand'], r['series'])].append(r)

    res = []
    for (b, s), v in sorted(agg.items()):
        kws = sorted({r['kw'] for r in v if r['kw']})
        bars = sorted({r['bar'] for r in v if r['bar']})
        ps = sorted(r['price'] for r in v if r['price'])
        own = sum(1 for r in v if r['price_src'] == 'наша')
        res.append(dict(brand=b, series=s, n=len(v),
                        kw_min=kws[0] if kws else None, kw_max=kws[-1] if kws else None,
                        bars=bars, price_min=ps[0] if ps else None,
                        price_max=ps[-1] if ps else None, priced=len(ps),
                        price_own=own, price_src='наша' if own else 'конкуренты',
                        sample=v[0]['name'][:70]))

    res.sort(key=lambda r: (r['brand'], -(r['n'])))
    json.dump(res, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    cur = None
    for r in res:
        if r['n'] < 3:                              # шум разбора имени, не серия
            continue
        if r['brand'] != cur:
            print(f"\n=== {r['brand']}"); cur = r['brand']
        kw = (f"{r['kw_min']:g}-{r['kw_max']:g}" if r['kw_min'] else '?')
        pr = (f"{r['price_min']:,.0f}-{r['price_max']:,.0f}".replace(',', ' ')
              if r['price_min'] else 'нет цен')
        bars = ','.join(f'{b:g}' for b in r['bars'][:6]) or '?'
        print(f"  {r['series']:<12} {r['n']:>4} поз  {kw:>12} кВт  {bars:>16} бар  {pr:>25} ₽")
    print(f"\nвсего позиций {len(rows)}, серий {len(res)}, сохранено в {a.out}")


if __name__ == '__main__':
    main()
