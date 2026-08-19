#!/usr/bin/env python3
"""Фаза 8: вторая ссылка там, где лимит площадки позволяет и есть смысл.

Замечание владельца 19.08: «одну ссылку туда можно было?» — у ess-ltd.ru карточка
разрешает три ссылки, а стояла одна. Проверка показала: 21 донор из 24 недоиспользует
лимит. При 44 целевых страницах на prokompressor и 24 донорах это прямая потеря —
денежное ядро (электрические и дизельные винтовые, airman, страницы по литражу)
остаётся без ссылок, хотя платить за них не нужно.

Правила, которые здесь соблюдаются:
* второй URL — обязательно ДРУГАЯ страница того же нашего сайта (правило «один донор —
  один наш сайт» и лимит темпа «одна ссылка на URL в две недели»);
* ссылка ставится, только если в статье есть раздел, куда она встаёт по смыслу.
  «Занять слот» нельзя: лишняя ссылка в покупной статье — первое, что видит редактор;
* якорь берётся из живых запросов второй страницы, как и первый.

Агент вправе ответить «не нужна» — это нормальный исход, а не провал.

    python3 second_link.py [донор ...]
"""
from __future__ import annotations

import concurrent.futures as cf
import json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gen_provider as gp                                    # noqa: E402
from plan_jobs import decisions, load                        # noqa: E402

OUT = os.environ.get('SECOND_OUT', 'second-links.json')

PROMPT = """=== РЕШЕНИЯ ВЛАДЕЛЬЦА (приоритет выше любых расчётов) ===
{decisions}

=== ЗАДАЧА ===
Реши, нужна ли этой статье ВТОРАЯ ссылка, и если да — на какую страницу и с каким якорем.

Площадка разрешает {max_links} ссылок в статье, сейчас стоит {have}. Платить за вторую
ссылку не нужно, она идёт в том же размещении. Но ставить её ради слота нельзя: лишняя
ссылка в покупной статье — первое, что замечает редактор площадки.

=== СТАТЬЯ ===
площадка: {donor} ({mode})
аудитория: {donor_note}
заголовок: {title}
угол: {angle}
скелет: {skeleton}

ПЕРВАЯ ссылка (не меняется): {url}
   якорь: {anchor}

=== КУДА МОЖНО ПОСТАВИТЬ ВТОРУЮ ===
Только страницы этого же нашего сайта — на другой сайт в одной статье ссылаться нельзя.
Страница обязана быть ДРУГОЙ, не той, что уже стоит.

{pages}

=== КАК РЕШАТЬ ===
* Вторая ссылка нужна, если в статье есть раздел, где вторая тема разбирается по
  существу — не упоминается вскользь, а обсуждается. Пример хорошей пары: статья про
  воздухоснабжение очистных, где один раздел про компрессорную станцию объекта, а
  другой про аэрацию: две ссылки, каждая в свой раздел.
* Вторая ссылка НЕ нужна, если статья держится на одной теме. Тогда честный ответ —
  «не нужна», и это нормально.
* Приоритет при выборе: страницы из ручного отбора владельца и денежное ядро, но
  только среди тех, что реально ложатся в текст.

=== ФОРМАТ ОТВЕТА (plain text, без markdown, ровно четыре строки) ===
РЕШЕНИЕ: нужна | не нужна
СТРАНИЦА: <полный URL со слешем в конце или «нет»>
ЯКОРЬ: <2-5 слов или «нет»>
ПОЧЕМУ: <одна строка: в какой раздел встаёт и почему это не «слот ради слота»>
"""


def pages_for_site(site, v15, pq, exclude, limit=14):
    rows = [r for r in v15 if r['site'] == site and r['page'].rstrip('/') != exclude.rstrip('/')]
    rows.sort(key=lambda r: -(float(r['money'] or 0)))
    out = []
    for r in rows[:limit]:
        q = pq.get((site, r['page']), {})
        anc = [a['q'] for a in (q.get('anchors_reach') or [])[:4]]
        money = int(float(r['money'] or 0))
        mark = ' | ПРИОРИТЕТ ВЛАДЕЛЬЦА' if r.get('manual') else ''
        out.append(f"  https://{site}{r['page']} | {money} ₽/мес{mark}"
                   + (f"\n      живые запросы: {'; '.join(anc)}" if anc else ''))
    return '\n'.join(out)


def one(args):
    j, prompt = args
    try:
        msg = gp.call(None, [{'role': 'user', 'content': prompt}],
                      model='claude-fable-5', attempts=4)
        raw = ''.join(b.text for b in msg.content if b.type == 'text').strip().replace('*', '')
    except Exception as e:                                   # noqa: BLE001
        return {'donor': j['donor'], 'error': repr(e)[:130]}
    g = lambda k: (re.search(rf'^{k}:\s*(.+)$', raw, re.M) or [None, ''])[1].strip()
    return {'donor': j['donor'], 'decision': g('РЕШЕНИЕ').lower(), 'url2': g('СТРАНИЦА'),
            'anchor2': g('ЯКОРЬ'), 'why': g('ПОЧЕМУ')}


def main():
    cards, v15, pq, sem, th = load()
    pq = {(r['site'], r['page']): r for r in json.load(open('plan-queries.json', encoding='utf-8'))}
    jobs = [json.loads(l) for l in open('final-jobs.jsonl', encoding='utf-8') if l.strip()]
    want = set(sys.argv[1:])
    tasks = []
    for j in jobs:
        if want and j['donor'] not in want:
            continue
        lim = int(str(cards.get(j['donor'], {}).get('max_links', '1')).strip() or 1)
        have = 1 + (1 if j.get('url2') else 0)
        if lim <= have:
            continue
        site, path = j['url'].replace('https://', '').split('/', 1)
        tasks.append((j, PROMPT.format(
            decisions=decisions(), max_links=lim, have=have, donor=j['donor'],
            mode=j.get('mode', ''), donor_note=(j.get('donor_note') or '')[:220],
            title=j.get('title', ''), angle=(j.get('angle') or '')[:420],
            skeleton=(j.get('skeleton') or '')[:300], url=j['url'], anchor=j['anchor'],
            pages=pages_for_site(site, v15, pq, '/' + path))))
    print('статей с запасом по лимиту:', len(tasks), flush=True)
    by = {j['donor']: j for j in jobs}
    res, added = [], 0
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        for r in ex.map(one, tasks):
            res.append(r)
            j = by[r['donor']]
            ok = (r.get('decision', '').startswith('нужна')
                  and r.get('url2', '').startswith('http')
                  and r['url2'].rstrip('/') != j['url'].rstrip('/')
                  and r.get('anchor2') and r['anchor2'] != 'нет')
            if ok:
                j['url2'], j['anchor2'] = r['url2'], r['anchor2']
                j['second_why'] = r['why']
                added += 1
            print('  %-28s %-10s %s' % (r['donor'], r.get('decision', 'ERR')[:10],
                                        (r.get('url2') or r.get('error') or '')[:56]), flush=True)
    json.dump(res, open(OUT, 'w'), ensure_ascii=False, indent=1)
    with open('final-jobs.jsonl', 'w', encoding='utf-8') as f:
        for j in jobs:
            f.write(json.dumps(j, ensure_ascii=False) + '\n')
    print('\nвторых ссылок добавлено: %d из %d возможных' % (added, len(tasks)))
    print('ссылок в кампании стало:', sum(1 + (1 if j.get('url2') else 0) for j in jobs))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
