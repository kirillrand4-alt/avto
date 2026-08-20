#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""План выкладки волны гост-постов.

    JOBS_MODULE=wave-jobs python3 plan_placements.py [--seed N] [--start YYYY-MM-DD]

Печатает календарь и переписывает PLACEMENT-PLAN.md.

Задача не «раскидать 24 статьи по дням», а не создать рисунок, по которому
размещения связываются между собой. Отсюда все ограничения ниже: каждое из них
закрывает свой способ спалиться.
"""
import argparse, collections, datetime, itertools, json, os, random, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gen_wave import JOBS

DIR = os.path.dirname(os.path.abspath(__file__))
RU = {'Mon': 'пн', 'Tue': 'вт', 'Wed': 'ср', 'Thu': 'чт', 'Fri': 'пт'}

PER_DOMAIN_WEEK = 2    # решение владельца 20.08: 2 статьи в неделю на акцепторный домен
PER_DAY_TOTAL   = 2    # по всей кампании: больше — читается как одна закупка
URL_COOLDOWN    = 14   # дней между двумя ссылками на один и тот же URL
DOMAIN_GAP      = 2    # дней между двумя статьями на один акцептор
HOLD_AFTER_WEEK = 4    # с какой недели выпускаем придержанные статьи

domain_of = lambda u: re.sub(r'https?://([^/]+).*', r'\1', u)


def spread_modes(items, rnd):
    """Разложить меньшинство по жанру равномерно, а не пачкой в конце очереди."""
    them = [x for x in items if x['mode'] != 'жанровый']
    genr = [x for x in items if x['mode'] == 'жанровый']
    rnd.shuffle(them); rnd.shuffle(genr)
    big, small = (genr, them) if len(genr) >= len(them) else (them, genr)
    if not small:
        return big
    step = (len(big) + 1) / (len(small) + 1)
    at = {round(step * (i + 1)) + i for i in range(len(small))}
    out, bi, si = [], 0, 0
    for pos in range(len(items)):
        if pos in at and si < len(small):
            out.append(small[si]); si += 1
        else:
            out.append(big[bi]); bi += 1
    return out


def build(seed, start):
    rnd = random.Random(seed)
    arts = [dict(slug=j['slug'], donor=j['donor'], mode=j.get('mode', 'тематический'),
                 dom=domain_of(j['links'][0][0]), urls=[u for u, _ in j['links']])
            for j in JOBS]
    by_dom = collections.defaultdict(list)
    for a in arts:
        by_dom[a['dom']].append(a)

    # Самый крупный акцептор задаёт длину кампании; у остальных одну статью
    # придерживаем на вторую половину, иначе хвост идёт подряд на один домен.
    biggest = max(by_dom, key=lambda d: len(by_dom[d]))
    queues, held = {}, {}
    for d, v in by_dom.items():
        q = spread_modes(v, rnd)
        if d != biggest and len(q) >= 2:
            held[d] = q.pop()
        queues[d] = q

    day_load, url_last, plan = collections.Counter(), {}, []
    last_mode = None

    def fits(a, dt):
        return (day_load[dt] < PER_DAY_TOTAL and
                all((dt - url_last[u]).days >= URL_COOLDOWN
                    for u in a['urls'] if u in url_last))

    week = 0
    while (any(queues.values()) or held) and week <= 60:
        ws = start + datetime.timedelta(weeks=week)
        if week + 1 >= HOLD_AFTER_WEEK and held:
            for d in list(held):
                if rnd.random() < 0.5:
                    queues[d].append(held.pop(d))
        active = [d for d in queues if queues[d]]
        for d in rnd.sample(active, len(active)):
            quota = min(rnd.choices([1, PER_DOMAIN_WEEK], weights=[0.2, 0.8])[0], len(queues[d]))
            # дни выбираем сразу на всю квоту недели: если брать по одному,
            # первый может сесть на четверг, и второму не хватит зазора до выходных
            if quota == 2:
                combos = [(i, j) for i in range(5) for j in range(5) if j - i >= DOMAIN_GAP]
            else:
                combos = [(i, None) for i in range(5)]
            rnd.shuffle(combos)
            slots = None
            for i, j in combos:
                cand = [ws + datetime.timedelta(days=i)]
                if j is not None:
                    cand.append(ws + datetime.timedelta(days=j))
                if all(day_load[dt] < PER_DAY_TOTAL for dt in cand):
                    slots = cand; break
            if not slots:
                continue
            for dt in slots:
                order = {id(x): k for k, x in enumerate(queues[d])}
                picks = sorted(queues[d], key=lambda x: (x['mode'] == last_mode, order[id(x)]))
                a = next((x for x in picks if fits(x, dt)), None)
                if a is None:
                    continue
                queues[d].remove(a)
                day_load[dt] += 1
                for u in a['urls']:
                    url_last[u] = dt
                plan.append(dict(date=dt, **a))
                last_mode = a['mode']
        week += 1

    for d, a in held.items():          # если придержанная так и не вышла - в конец
        plan.append(dict(date=plan[-1]['date'] + datetime.timedelta(days=3), **a))
    plan.sort(key=lambda x: (x['date'], x['dom']))
    return plan, day_load


def check(plan, day_load, start):
    """Проверки инвариантов: план без них — просто список дат."""
    bad = []
    per = collections.Counter((p['dom'], (p['date'] - start).days // 7) for p in plan)
    bad += [f'{d}: {n} за неделю {w + 1}' for (d, w), n in per.items() if n > PER_DOMAIN_WEEK]
    bad += [f'{dt}: {n} публикаций в день' for dt, n in day_load.items() if n > PER_DAY_TOTAL]
    seen = {}
    for p in plan:
        for u in p['urls']:
            if u in seen and (p['date'] - seen[u]).days < URL_COOLDOWN:
                bad.append(f'{u}: две ссылки за {(p["date"] - seen[u]).days} дней')
            seen[u] = p['date']
    bad += [f'{p["date"]}: выходной' for p in plan if p['date'].weekday() > 4]
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seed', type=int, default=20260820)
    ap.add_argument('--start', default='2026-08-24')
    ap.add_argument('--no-write', action='store_true')
    a = ap.parse_args()
    start = datetime.date.fromisoformat(a.start)
    plan, day_load = build(a.seed, start)

    bad = check(plan, day_load, start)
    wk = collections.Counter((p['date'] - start).days // 7 + 1 for p in plan)
    seq = ''.join('Ж' if p['mode'] == 'жанровый' else 'Т' for p in plan)
    runs = max(len(list(g)) for _, g in itertools.groupby(seq))

    cur = None
    for p in plan:
        w = (p['date'] - start).days // 7 + 1
        if w != cur:
            print(f'\n── неделя {w} ({wk[w]}) ' + '─' * 44); cur = w
        print(f"   {p['date'].strftime('%d.%m')} {RU[p['date'].strftime('%a')]}  "
              f"{p['dom']:22s} {p['donor']:27s} "
              f"{'жанр' if p['mode'] == 'жанровый' else 'тема'}  {p['slug'][:42]}")
    print(f'\nразмещений {len(plan)} за {max(wk)} недель, по неделям: '
          + ' → '.join(str(wk[w]) for w in sorted(wk)))
    print(f'макс. серия одного типа подряд: {runs}')
    print('нарушения инвариантов:', bad or 'нет')
    if bad:
        sys.exit('план не прошёл собственные проверки')

    if not a.no_write:
        p = os.path.join(DIR, 'placement-plan.json')
        json.dump([{**x, 'date': x['date'].isoformat()} for x in plan],
                  open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print('сохранено:', os.path.relpath(p, DIR))


if __name__ == '__main__':
    main()
