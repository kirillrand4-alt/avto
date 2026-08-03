# -*- coding: utf-8 -*-
"""Чистый топ акцепторов v4 (задание владельца):
1) Позиция страницы — взвешенная по ПОКАЗАМ РЕЛЕВАНТНЫХ ключей (запросный срез),
   брендовые/мусорные запросы исключены из средней; по ПС раздельно.
2) Прогноз — от живых КЛИКОВ (показы с ботами не участвуют вовсе):
   gain = клики_рел × (CTR_live(топ-5)/CTR_live(поз) − 1) × feasibility.
   Живые кривые — DATA-QUALITY-FRESH §10.1 (моб-якоря + дневная форма).
3) Чек — только из выгрузок (битрикс-экспорт, прайс, цены страницы), источник пишем.
4) Анкоры — реальные запросы страницы в зоне роста (поз. 4–20 с показами).
Вход: fresh-query CSV (уровень query из /stat/api/export-all).
Выход: acceptor-clean.json + печать топа.
"""
import csv, json, os, re, sys
from collections import defaultdict

import acceptor_value as v2

DIR = os.path.dirname(os.path.abspath(__file__))
QUERY_CSV = sys.argv[1] if len(sys.argv) > 1 else 'fresh-query-30d.csv'

NET = {'prokompressor.ru', 'nsk.prokompressor.ru', 'barnaul.prokompressor.ru',
       'vladivostok.prokompressor.ru', 'enger-air.ru', 'zif-kompressor.ru',
       'berg-compressor.com', 'berg-kompressor.ru', 'abac-kompressor.ru',
       'ekomak-kompressor.com', 'ekomak-compressor.com', 'crossair-compressor.ru',
       'dali-kompressor.ru', 'remeza-kompressor.ru', 'kraftmann-kompressor.com',
       'fini-compressor.com', 'ironmac-compressor.com', 'ac-kompressor.ru',
       'comaro-kompressor.ru', 'oil-free.ru', 'cmprg.ru', 'dizel-compressor.ru'}
BRAND_RX = re.compile(r'berg|берг|dali|дали|enger|энгер|енгер|zif|зиф|ekomak|экомак|'
                      r'remeza|ремеза|abac|абак|comaro|комаро|crossair|кросс?[\s-]?эйр|'
                      r'kraftmann|крафтман|fini|фини|ironmac|prokompressor|прокомпрессор|'
                      r'руспром|rusprom|oil[\s-]?free|cmprg', re.I)

# токены релевантности по сегментам URL (запрос обязан содержать хотя бы один)
SEG_TOKENS = {
    'vint_el': ['винтов'], 'bezmasl': ['безмасл', 'спиральн', 'центробеж', 'турбокомпрессор'],
    'vd_buster': ['высок', 'давлен', 'бустер', 'дожим', 'бар'],
    'vint_diz': ['дизел', 'передвиж', 'шасси', 'прицеп'],
    'gen_azot': ['азот'], 'gen_kislorod': ['кислород'],
    'osush_ads': ['осушит', 'адсорб'], 'osush_mix': ['осушит', 'рефриж', 'точк'],
    'resivery': ['ресивер', 'воздухосборн'], 'vozduhoduvki': ['воздуходув', 'газодув'],
    'porshn': ['поршн'], 'filtry': ['фильтр', 'сепаратор', 'масл'],
    'mks': ['станци', 'модульн', 'мкс'],
}
GENERIC = ['компрессор']   # для главных/смешанных страниц

# живые кривые (§10.1, сглажено) — мультипликатор кликов при подъёме в топ-5
LIVE = {
    'Google': [(2.5, 20.0), (4.5, 9.0), (7.5, 6.5), (9.5, 3.0), (10.5, 2.0), (12.5, 1.5), (15.5, 1.6), (20.5, 1.2), (30.5, 0.4)],
    'Яндекс': [(2.5, 24.0), (4.5, 9.0), (7.5, 5.0), (9.5, 2.0), (10.5, 1.4), (12.5, 1.5), (15.5, 1.2), (20.5, 0.6), (30.5, 0.6)],
}
TARGET = {'Google': 6.5, 'Яндекс': 5.0}

def ctr_live(src, pos):
    for hi, v in LIVE[src]:
        if pos < hi:
            return v
    return None

def live_shows_q(src, cl, sh, pos):
    """Пер-запросный бот-фильтр показов: клики валидируют показы против живой
    кривой. Если ожидаемых живых кликов >=3, а фактических меньше четверти —
    излишек показов боты (сканеры долбят конкретные ключи)."""
    c = ctr_live(src, max(pos, 1.0))
    if not c:
        return sh, False
    exp = sh * c / 100.0
    if exp >= 3 and cl < 0.25 * exp:
        return max(cl / (c / 100.0), 0.05 * sh), True
    return sh, False


def feas(p):
    if p <= 10: return 1.0
    if p <= 15: return 0.7
    if p <= 20: return 0.5
    if p <= 30: return 0.3
    return 0.0


def tokens_for(url, site):
    seg_key, seg_name = v2.segment(url)
    path = url.split('//', 1)[-1]
    is_home = path.rstrip('/').count('/') == 0
    if is_home or seg_name == 'Бренд/категория (смеш.)':
        toks = list(SEG_TOKENS.get(seg_key, [])) + GENERIC if not is_home else GENERIC
    else:
        toks = SEG_TOKENS.get(seg_key, GENERIC)
    return seg_key, seg_name, toks, is_home


def main():
    price = v2.load_prices()
    bx = json.load(open(os.path.join(DIR, 'bitrix-prices.json')))
    payload_prices = v2.load_payload_prices()
    bots = {(b['site'], b['url'].rstrip('/'))
            for b in json.load(open(os.path.join(DIR, 'acceptor-value-fresh.json')))['bot_pages']}

    # запросный срез: дедуп (src,site,url,query) максимумом показов
    best = {}
    with open(QUERY_CSV, encoding='utf-8-sig') as f:
        rd = csv.reader(f); next(rd)
        for r in rd:
            src, site, url, q = r[0], v2.norm_site(r[1]), r[2].strip().rstrip('/'), r[3].strip().lower()
            if site not in NET or '?' in url or not url.startswith('http'):
                continue
            if re.search(r'\.(pdf|docx?|xlsx?|jpg|png)$|/docs/|/upload/|/company/docs', url, re.I):
                continue                     # файлы/документы — не акцепторы
            if src == 'Яндекс' and site == 'berg-compressor.com':
                continue                     # накрутка ПФ: клики фейковые
            if src == 'Google' and (site, url) in bots:
                continue
            try:
                cl, sh, pos = int(float(r[4] or 0)), int(float(r[5] or 0)), float(r[7] or 0)
            except ValueError:
                continue
            if sh <= 0 or pos <= 0:
                continue
            k = (src, site, url, q)
            if k not in best or sh > best[k][1]:
                best[k] = (cl, sh, pos)

    pages = defaultdict(lambda: defaultdict(list))   # (site,url) -> src -> [(q,cl,sh,pos)]
    for (src, site, url, q), (cl, sh, pos) in best.items():
        pages[(site, url)][src].append((q, cl, sh, pos))

    out = []
    for (site, url), by_src in pages.items():
        seg_key, seg_name, toks, is_home = tokens_for(url, site)
        kind = ('инфо' if re.search(r'/blog/|/poleznoe/|/news/|/stati/|instrukts|dokumentats', url)
                else 'главная' if is_home else 'каталог')
        if kind == 'инфо':
            continue
        rec = dict(url=url, site=site, segment=seg_name, seg_key=seg_key, kind=kind)
        tot_gain = 0.0; anchors = []
        for src in ('Google', 'Яндекс'):
            rows = by_src.get(src, [])
            rel = [r for r in rows if any(t in r[0] for t in toks) and not BRAND_RX.search(r[0])]
            rel = [(q, cl, sh, p) + live_shows_q(src, cl, sh, p) for q, cl, sh, p in rel]
            shows = sum(r[2] for r in rel); clicks = sum(r[1] for r in rel)
            live_sh = sum(r[4] for r in rel)
            if live_sh < 30:
                rec[src] = None
                continue
            pos = sum(r[3] * r[4] for r in rel) / live_sh   # позиция по ЖИВЫМ показам
            mult_now = ctr_live(src, max(pos, 5.0))
            gain = 0.0
            if 3.5 <= pos <= 30 and mult_now:
                gain = clicks * max(0.0, TARGET[src] / mult_now - 1) * feas(pos)
            rec[src] = dict(pos=round(pos, 1), rel_shows=shows, rel_live_shows=round(live_sh),
                            rel_clicks=clicks, n_queries=len(rel), gain=round(gain, 1))
            tot_gain += gain
            for q, cl, sh, p, lsh, botq in rel:
                if 3.5 <= p <= 20 and lsh >= 10:
                    anchors.append((q, src, round(p, 1), round(lsh), sh, cl, botq))
        if tot_gain <= 0:
            continue
        chek, chek_src = v2.resolve_chek(url, site, seg_key, price, bx, payload_prices)
        boost, brand = v2.brand_boost(url, site)
        seen = set(); uniq = []
        for a in sorted(anchors, key=lambda a: (-a[3], -a[5])):
            if a[0] in seen:
                continue
            seen.add(a[0]); uniq.append(a)
        rec.update(price=chek, chek_src=chek_src, brand=brand,
                   gain=round(tot_gain, 1),
                   value=round(tot_gain * chek / 1e6 * boost, 1),
                   anchors=uniq[:8])
        out.append(rec)
    out.sort(key=lambda r: -r['value'])
    json.dump(out, open(os.path.join(DIR, 'acceptor-clean.json'), 'w'),
              ensure_ascii=False, indent=1)

    print(f'страниц с релевантным потенциалом: {len(out)}')
    for i, r in enumerate(out[:25], 1):
        g, y = r.get('Google'), r.get('Яндекс')
        gs = f"G {g['pos']} ({g['rel_clicks']}кл/{g['rel_shows']}пок, +{g['gain']})" if g else 'G —'
        ys = f"Y {y['pos']} ({y['rel_clicks']}кл/{y['rel_shows']}пок, +{y['gain']})" if y else 'Y —'
        print(f"\n{i:>2}. value {r['value']:>6.1f} | чек {r['price']:,} ({r['chek_src']}) | {gs} | {ys}")
        print(f"    {r['url']}")
        for q, src, p, lsh, sh, cl, botq in r['anchors'][:4]:
            print(f"      анкор: «{q}» [{src} поз {p}, живых {lsh}/{sh} пок, {cl} кл{' БОТЫ' if botq else ''}]")


if __name__ == '__main__':
    main()
