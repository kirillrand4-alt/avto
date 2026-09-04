# -*- coding: utf-8 -*-
"""Этап 1: механические проверки по всем разделам. Без ИИ, без токенов.

Вход:  inventory.jsonl (этап 0), keys-by-url.json + cannibals.json (этап 0б),
       ../gen/payload-*.json (факты и числа), link-codes.json (коды ссылок)
Выход: checks.jsonl - по строке на раздел с жёсткими фактами для отчёта.
"""
import json, os, re, glob, collections, html

HERE = os.path.dirname(os.path.abspath(__file__))
GEN = os.path.join(HERE, '..', 'gen')

TITLE_MIN, TITLE_MAX = 30, 70
DESC_MIN, DESC_MAX = 70, 160


def load_jsonl(p):
    out = []
    if os.path.exists(p):
        for line in open(p, encoding='utf-8'):
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def main():
    inv = load_jsonl(os.path.join(HERE, 'inventory.jsonl'))
    keys = json.load(open(os.path.join(HERE, 'keys-by-url.json')))
    cann = json.load(open(os.path.join(HERE, 'cannibals.json')))
    codes = {}
    lp = os.path.join(HERE, 'link-codes.json')
    if os.path.exists(lp):
        codes = json.load(open(lp))

    pay = {}
    for f in glob.glob(os.path.join(GEN, 'payload-*.json')):
        d = json.load(open(f))
        pay['https://prokompressor.ru' + d['url']] = d

    # дубли метатегов по сайту
    tcnt = collections.Counter(r['title'].strip() for r in inv if r['title'].strip())
    dcnt = collections.Counter(r['description'].strip() for r in inv if r['description'].strip())
    # повторы FAQ-вопросов
    faq = collections.Counter()
    for r in inv:
        for q in faq_questions(r):
            faq[q] += 1

    out = open(os.path.join(HERE, 'checks.jsonl'), 'w', encoding='utf-8')
    for r in inv:
        u, p = r['url'], r['path']
        k = keys.get(u, {})
        c = {'url': u, 'path': p, 'depth': r['depth'], 'h1': r['h1'],
             'article_kind': r['article_kind'], 'article_chars': r['article_chars'],
             'h2_count': len(r['h2']), 'faq_schema': r['has_faq_schema'],
             'byline': r['byline'], 'flags': [], 'notes': []}

        # 1. наличие статьи
        if r['article_kind'] == 'none':
            c['flags'].append('НЕТ_СТАТЬИ')
        elif r['article_kind'] == 'legacy':
            c['flags'].append('СТАТЬЯ_НЕ_НАША')
        elif r['article_chars'] < 2500:
            c['flags'].append('СТАТЬЯ_КОРОТКАЯ')

        # 2. метатеги
        t, d = r['title'].strip(), r['description'].strip()
        if not t:
            c['flags'].append('TITLE_ПУСТОЙ')
        elif not (TITLE_MIN <= len(t) <= TITLE_MAX):
            c['flags'].append(f'TITLE_ДЛИНА_{len(t)}')
        if not d:
            c['flags'].append('DESC_ПУСТОЙ')
        elif not (DESC_MIN <= len(d) <= DESC_MAX):
            c['flags'].append(f'DESC_ДЛИНА_{len(d)}')
        if t and tcnt[t] > 1:
            c['flags'].append(f'TITLE_ДУБЛЬ_x{tcnt[t]}')
        if d and dcnt[d] > 1:
            c['flags'].append(f'DESC_ДУБЛЬ_x{dcnt[d]}')
        if r['canonical'] and r['canonical'].rstrip('/') != u.rstrip('/'):
            c['flags'].append('CANONICAL_ЧУЖОЙ')
            c['notes'].append('canonical -> ' + r['canonical'])

        # 3. стайлгайд
        b = r.get('article_html', '')
        if '—' in b:
            c['flags'].append('ДЛИННОЕ_ТИРЕ')
        if re.search(r'<ul[\s>]', b, re.I):
            c['flags'].append('ТЕГ_UL')

        # 4. ссылки
        bad = [l for l in r['article_links'] if codes.get(l, 200) >= 400 or codes.get(l) == 0]
        selfl = [l for l in r['article_links'] if l.rstrip('/') == p.rstrip('/')]
        c['links_total'] = len(r['article_links'])
        c['links_bad'] = bad
        if bad:
            c['flags'].append(f'БИТЫХ_ССЫЛОК_{len(bad)}')
        if selfl:
            c['flags'].append('ССЫЛКА_НА_СЕБЯ')

        # 5. числа против payload
        pd = pay.get(u)
        c['has_payload'] = bool(pd)
        if pd and b:
            nums = set(int(x.replace(' ', '').replace(' ', ''))
                       for x in re.findall(r'\b\d[\d  ]{2,9}\b', html.unescape(re.sub(r'<[^>]+>', ' ', b))))
            pmax = pd.get('price_max')
            if pmax:
                over = [n for n in nums if 100000 < n < 100000000 and n > pmax * 1.05]
                if over:
                    c['flags'].append('ЦЕНА_ВЫШЕ_ВЫГРУЗКИ')
                    c['notes'].append(f'price_max={pmax}, в тексте {sorted(over)[:3]}')

        # 6. каннибализация
        cn = cann.get(u, [])
        c['cannibal_queries'] = len(cn)
        c['cannibal_top'] = cn[:5]
        if len(cn) >= 5:
            c['flags'].append(f'КАННИБАЛИЗАЦИЯ_{len(cn)}')

        # 7. повторы FAQ
        rep = [q for q in faq_questions(r) if faq[q] >= 8]
        c['faq_repeated'] = rep
        if rep:
            c['flags'].append(f'FAQ_ПОВТОР_{len(rep)}')

        # трафик и приоритет
        ya = k.get('Яндекс', {}); go = k.get('Google', {})
        c['shows'] = k.get('shows_total', 0)
        c['clicks'] = k.get('clicks_total', 0)
        c['zone_11_30_shows'] = k.get('zone_11_30_shows', 0)
        c['ctr_gap_clicks'] = 0
        for e in (ya, go):
            if e.get('shows') and e.get('wpos'):
                exp = 0.093 * e['wpos'] ** -0.97
                c['ctr_gap_clicks'] += max(0, round(exp * e['shows'] - e['clicks']))
        c['priority'] = priority(c)
        out.write(json.dumps(c, ensure_ascii=False) + '\n')
    out.close()

    flags = collections.Counter(f.split('_x')[0].rstrip('0123456789_') for r in load_jsonl(os.path.join(HERE, 'checks.jsonl')) for f in r['flags'])
    print('разделов проверено:', len(inv))
    for f, n in flags.most_common():
        print(f'  {f:<28} {n}')


def faq_questions(r):
    b = r.get('article_html', '')
    if not b:
        return []
    qs = re.findall(r'<summary[^>]*>(.*?)</summary>', b, re.S | re.I)
    qs += re.findall(r'"name"\s*:\s*"([^"]{10,140}\?)"', b)
    return [html.unescape(re.sub(r'<[^>]+>', '', q)).strip().lower() for q in qs]


def priority(c):
    if c['article_kind'] == 'none' and c['shows'] > 100:
        return 0
    if c['zone_11_30_shows'] > 300 or c['ctr_gap_clicks'] > 20:
        return 1
    if c['shows'] > 50 or c['flags']:
        return 2
    return 3


if __name__ == '__main__':
    main()
