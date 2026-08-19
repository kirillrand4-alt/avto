#!/usr/bin/env python3
"""Фаза 3: раскладка ссылок по страницам — один агент видит сразу все пары.

Проблема, которую решает этот проход. Оценка фита (`fit_score.py`) спрашивает каждого
агента про его площадку отдельно, и агент не знает, что выбрали остальные. В итоге
первая раскладка дала перекос: `/po-tipu/vintovye/` (72 152 ₽/мес, позиция падает)
собрала ВОСЕМЬ жанровых ссылок с площадок про мемы и цитаты, а денежное ядро —
электрические и дизельные винтовые, airman, страницы по литражу, лазерная резка,
atlas-copco — не получило ни одной. Распределение считало фит донора к сайту, но
ценность самой страницы в расчёт не входила.

Здесь агент видит ВСЕ пары разом (тематические с фитом и жанровые с готовыми темами)
и все страницы с деньгами, поэтому может разложить осмысленно: сильные доноры на
приоритетные страницы владельца, жанровые — туда, где их тема хоть как-то ложится.

    python3 dispatch_pages.py
"""
from __future__ import annotations

import json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gen_provider as gp                                    # noqa: E402
from plan_jobs import decisions                              # noqa: E402

OUT = os.environ.get('DISPATCH_OUT', 'dispatch.json')
MAX_PER_PAGE = 2

PROMPT = """=== РЕШЕНИЯ ВЛАДЕЛЬЦА (приоритет выше любых расчётов) ===
{decisions}

=== ЗАДАЧА ===
Ты раскладываешь ссылки по страницам. Пары «донор -> наш сайт» уже назначены и НЕ
меняются: твоё дело — решить, на КАКУЮ СТРАНИЦУ этого сайта поставить ссылку из
каждой статьи, и каким якорем.

=== ПАРЫ, КОТОРЫЕ НАДО РАЗЛОЖИТЬ ===
{pairs}

=== СТРАНИЦЫ ===
{pages}

=== ПРАВИЛА ===
1. **Приоритетные страницы владельца получают ЛУЧШИХ доноров** — тех, у кого выше
   фит и чья тема ближе. Не отдавай их жанровым статьям, если есть тематический донор.
2. **Не больше {maxpp} ссылок на одну страницу.** Дальше упирается лимит темпа
   (одна ссылка на URL в две недели).
3. **Денежное ядро не должно остаться пустым.** Если после приоритетных страниц
   остались сильные доноры — веди их на страницы с большим прогнозом дохода, а не
   на всё подряд.
4. Страница должна быть осмысленной для темы статьи. Статья про лазерную резку ведёт
   на компрессоры для лазерной резки, а не на ресиверы. Если для жанровой статьи
   идеальной страницы нет — бери ближайшую по смыслу из оставшихся, это нормально.
5. Якорь: для тематических доноров — коммерческий или точный из готовых по странице;
   для жанровых — только брендовый («Компрессор Центр», «BERG», «ENGER») или
   безанкорный (домен).
6. Все URL — со слешем в конце.

=== ФОРМАТ ОТВЕТА (строго, plain text, одна строка на донора, без markdown) ===
<донор> | <полный URL страницы со слешем> | <текст якоря> | <одна строка: почему эта страница>
"""


def load():
    assign = json.load(open('assignment.json', encoding='utf-8'))
    genre = [json.loads(l) for l in open('genre-jobs.jsonl', encoding='utf-8')
             if l.strip() and not json.loads(l).get('error')]
    v15 = json.load(open('acceptors-v15.json', encoding='utf-8'))
    return assign, genre, v15


def pairs_block(assign, genre):
    out = ['ТЕМАТИЧЕСКИЕ (статья — отраслевой разбор, фит показывает силу пары):']
    for d, a in sorted(assign.items(), key=lambda kv: -kv[1]['score']):
        out.append(f"  {d} -> {a['site']} | фит {a['score']}/10 | {a['why'][:110]}")
    out.append('')
    out.append('ЖАНРОВЫЕ (статья в жанре площадки, ссылка стоит справкой):')
    for r in genre:
        site = (r.get('url') or '').replace('https://', '').split('/')[0]
        out.append(f"  {r['donor']} -> {site} | тема: {r.get('title', '')[:90]}")
    return '\n'.join(out)


def pages_block(v15, sites):
    out = []
    for site in sites:
        rows = [r for r in v15 if r['site'] == site]
        rows.sort(key=lambda r: -(float(r['money'] or 0)))
        out.append(f'--- {site} ---')
        for r in rows:
            money = int(float(r['money'] or 0))
            anc = [a for a in (r['anchors'] or {}).values() if a]
            mark = ' | ПРИОРИТЕТ ВЛАДЕЛЬЦА' if r.get('manual') else ''
            out.append(f"  https://{site}{r['page']} | {money} ₽/мес | "
                       f"позиция {r['pos_google']}{mark}\n      якоря: {' | '.join(anc[:4])}")
    return '\n'.join(out)


def main():
    assign, genre, v15 = load()
    sites = sorted({a['site'] for a in assign.values()} |
                   {(r.get('url') or '').replace('https://', '').split('/')[0] for r in genre})
    sites = [s for s in sites if s]
    prompt = PROMPT.format(decisions=decisions(), pairs=pairs_block(assign, genre),
                           pages=pages_block(v15, sites), maxpp=MAX_PER_PAGE)
    print('пар на раскладку:', len(assign) + len(genre), '| промпт', len(prompt), 'символов',
          flush=True)
    msg = gp.call(None, [{'role': 'user', 'content': prompt}], model='claude-fable-5', attempts=4)
    raw = ''.join(b.text for b in msg.content if b.type == 'text').strip()
    known = set(assign) | {r['donor'] for r in genre}
    res = []
    for line in raw.replace('*', '').split('\n'):
        parts = [p.strip() for p in line.split('|')]
        if len(parts) < 3 or parts[0] not in known:
            continue
        res.append({'donor': parts[0], 'url': parts[1], 'anchor': parts[2],
                    'why': parts[3] if len(parts) > 3 else '',
                    'mode': 'тематический' if parts[0] in assign else 'жанровый'})
    json.dump(res, open(OUT, 'w'), ensure_ascii=False, indent=1)
    import collections
    per = collections.Counter(r['url'].rstrip('/') for r in res)
    print('разложено:', len(res), 'из', len(known))
    over = [(u, n) for u, n in per.items() if n > MAX_PER_PAGE]
    if over:
        print('ПРЕВЫШЕН лимит на страницу:', over)
    miss = known - {r['donor'] for r in res}
    if miss:
        print('не разложены:', miss)
    for r in sorted(res, key=lambda x: x['url']):
        print('  %-28s %-58s %s' % (r['donor'], r['url'].replace('https://', '')[:58],
                                    r['anchor'][:34]))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
