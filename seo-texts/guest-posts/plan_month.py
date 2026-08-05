#!/usr/bin/env python3
"""Месячная раскладка размещений: 10 доноров приоритета владельца -> страницы-акцепторы.

Задача владельца (05.08.2026): доноры 1-10 из donors-prioritized.xlsx, размещение за
1 месяц, 1-3 ссылки в статье, доля Enger:ProKompressor = 40:60, каждый дилерский домен
использован минимум 1 раз.

Скрипт не «предлагает вариант», а перебирает допустимые раскладки при жёстких
ограничениях (квоты акцепторов, круг очереди, темп, донор-фит) и ранжирует по
качеству фита. Запуск: python3 plan_month.py [-o month-plan.json]
"""
from __future__ import annotations

import argparse
import itertools
import json
import random
from dataclasses import dataclass, field

# --------------------------------------------------------------------------- #
# Акцепторы (нумерация FINAL-ACCEPTORS.md после правки владельца 05.08, ядро 17)
# --------------------------------------------------------------------------- #

ACCEPTORS = {
    1:  ('enger',  'enger-air.ru/catalog/vintovye_kompressory',                     2, 'винтовые'),
    2:  ('enger',  'enger-air.ru/catalog/kislorodnye-ustanovki',                    2, 'кислородные станции'),
    3:  ('enger',  'enger-air.ru/…/adsorbtsionnye_osushiteli',                      2, 'адсорбционные осушители'),
    4:  ('enger',  'enger-air.ru/catalog/bezmaslyanye_kompressory',                 2, 'безмасляные'),
    5:  ('enger',  'enger-air.ru/catalog/azotnye-ustanovki',                        2, 'азотные станции'),
    6:  ('prokom', 'prokompressor.ru/…/kompressory-200-bar',                        2, 'компрессоры 200 бар'),
    7:  ('prokom', 'prokompressor.ru/…/kompressornye-stantsii-szhatogo-vozdukha',   2, 'компрессорные станции'),
    8:  ('prokom', 'prokompressor.ru/…/kompressornye-stantsii…/mks',                2, 'модульные КС'),
    9:  ('enger',  'enger-air.ru/…/peredvizhnye-kompressory/dizelnye-kompressory',  2, 'дизельные передвижные'),
    10: ('prokom', 'prokompressor.ru/services',                                     2, 'сервис / пневмоаудит'),
    11: ('enger',  'enger-air.ru/…/azotnye-ustanovki/generatory_azota',             1, 'генераторы азота'),
    12: ('prokom', 'prokompressor.ru/…/po-tipu/vintovye',                           1, 'винтовые'),
    13: ('enger',  'enger-air.ru/…/refrizheratornye_osushiteli',                    1, 'рефрижераторные осушители'),
    14: ('enger',  'enger-air.ru/catalog/mks',                                      1, 'МКС Enger'),
    15: ('prokom', 'prokompressor.ru/…/po-tipu/vintovye/dizelnye',                  1, 'дизельные винтовые'),
    16: ('enger',  'enger-air.ru/…/kislorodnye-ustanovki/generator-kisloroda',      1, 'генератор кислорода'),
    17: ('prokom', 'prokompressor.ru/…/vintovye/kompressory-40-bar',                1, 'винтовые 40 бар'),
}

# Ссылки, уже записанные в PLACEMENTS-LOG.md (волна 1). Съедают квоту независимо
# от того, размещается статья в этом месяце или нет.
PRIOR = {1: 1, 2: 1, 5: 1, 9: 1, 10: 1, 11: 1, 12: 1, 15: 1, 16: 1}

DEALERS = {
    'berg':     ('berg-compressor.com/catalog/vintovye-kompressory',            'винтовые'),
    'zif':      ('zif-kompressor.ru/catalog',                                   'взрывозащищённые / промышленные'),
    'dali':     ('dali-kompressor.ru/catalog/vintovye-kompressory',             'винтовые, бюджетный сегмент'),
    'remeza':   ('remeza-kompressor.ru/catalog/kompressory',                    'поршневые и малые МКС'),
    'crossair': ('crossair-compressor.ru/catalog/vintovye-kompressory',         'винтовые'),
    'ac':       ('ac-kompressor.ru/catalog/dizelnye-kompressory-do-8-bar/…',    'дизельные передвижные'),
}

# --------------------------------------------------------------------------- #
# Доноры приоритета владельца (donors-prioritized.xlsx, лист «Топ ProKompressor»)
# --------------------------------------------------------------------------- #


@dataclass
class Donor:
    prio: int
    domain: str
    profile: str
    # fit: акцептор -> балл. base = из матрицы донор-фита FINAL-ACCEPTORS.md,
    # ext = расширение этой сессии (помечается в отчёте, требует взгляда владельца)
    base: dict = field(default_factory=dict)
    ext: dict = field(default_factory=dict)
    dealers: dict = field(default_factory=dict)
    fixed: list | None = None          # готовая статья: ссылки менять нельзя
    article: str = ''
    note: str = ''

    def fit(self, a: int) -> float | None:
        if a in self.base:
            return self.base[a]
        if a in self.ext:
            return self.ext[a] - 1.5      # штраф за то, что это не матрица владельца
        return None


DONORS = [
    Donor(1, 'kineshemec.ru', 'промышленность Ивановской обл. (текстиль, машиностроение)',
          base={1: 9, 3: 8, 4: 7, 7: 8, 8: 7, 15: 9, 12: 8, 9: 9},
          dealers={'zif': 8, 'dali': 7, 'berg': 6},
          fixed=[9, 15], article='gp-dizel-na-strojke.html',
          note='статья готова (волна 1), ссылки зашиты в вёрстку'),
    Donor(2, 'samaraonline24.ru', 'промрегион: заводы, нефтехим, автосервисы',
          base={12: 9, 1: 8, 6: 8, 7: 8, 8: 7, 13: 7},
          dealers={'berg': 8, 'crossair': 7, 'dali': 6},
          fixed=[12], article='gp-podbor-vintovogo.html',
          note='пилот; статья готова'),
    Donor(3, 'operativa.ru', 'AI, автоматизация, «умное производство»',
          base={10: 9, 4: 8, 8: 7, 14: 6},
          dealers={'berg': 5, 'crossair': 5},
          fixed=[10], article='gp-vozduh-po-schetchiku.html',
          note='статья готова; пневмоаудит'),
    Donor(4, 'moscow-baku.ru', 'промсотрудничество РФ-Азербайджан, экспортные проекты',
          base={7: 9, 8: 9, 14: 7, 5: 6, 2: 6},
          ext={17: 7},
          dealers={'zif': 9, 'berg': 6, 'crossair': 5}),
    Donor(5, 'new-sebastopol.com', 'судоремонт, стройка, промобъекты',
          base={6: 9, 7: 8, 9: 8, 15: 8},
          ext={17: 8, 8: 6},
          dealers={'ac': 9, 'zif': 7, 'berg': 5}),
    Donor(6, 'oteplicah.com', 'теплицы, АПК, послеуборочная обработка',
          base={5: 9, 11: 9, 2: 7, 16: 7, 9: 7},
          ext={3: 7, 4: 6},
          dealers={'ac': 7, 'dali': 6, 'remeza': 6}),
    Donor(7, 'ftimes.ru', 'производственная экономика, издержки предприятий',
          base={10: 9, 1: 8, 7: 8, 13: 8},
          ext={12: 7, 6: 6},
          dealers={'berg': 8, 'crossair': 7}),
    Donor(8, 'gazetagavrilovka.ru', 'мастерская, ферма, малое производство',
          base={1: 8, 9: 9, 15: 8},
          ext={13: 7, 3: 6},
          dealers={'remeza': 9, 'ac': 8, 'dali': 7}),
    Donor(9, 'krasnodar.bz', 'АПК Кубани, послеуборочная обработка',
          base={5: 9, 11: 9, 2: 7, 16: 7, 9: 8},
          ext={8: 6, 3: 6},
          dealers={'ac': 7, 'dali': 6, 'crossair': 5}),
    Donor(10, 'arh112.ru', 'инвестиции в оборудование, окупаемость переработки',
          base={5: 7, 11: 7, 2: 6, 16: 6, 9: 7},
          ext={10: 9, 12: 6},
          dealers={'remeza': 6, 'crossair': 6, 'berg': 5}),
]

FREE = [d for d in DONORS if d.fixed is None]
FIXED = [d for d in DONORS if d.fixed is not None]

MAX_LINKS = 3
MIN_LINKS = 1
TARGET_RATIO = (0.40, 0.60)          # enger : prokompressor

pool: dict = {}                      # все допустимые раскладки прогона -> для альтернатив


# --------------------------------------------------------------------------- #

def capacity() -> dict:
    """Свободная квота каждого акцептора после волны 1 и готовых статей."""
    cap = {}
    for a, (_, _, quota, _) in ACCEPTORS.items():
        cap[a] = quota - PRIOR.get(a, 0)
    return cap


def fixed_links() -> list:
    out = []
    for d in FIXED:
        for a in d.fixed:
            out.append((d, a))
    return out


def enumerate_sets(d: Donor, cap: dict, max_core: int):
    """Все допустимые наборы core-ссылок донора (по фиту и остатку квоты)."""
    cands = [a for a in ACCEPTORS if d.fit(a) is not None and cap.get(a, 0) > 0]
    sets = []
    for n in range(1, min(max_core, len(cands)) + 1):
        for combo in itertools.combinations(cands, n):
            # два URL одного нашего сайта в статье допустимы, трёх не бывает
            sites = [ACCEPTORS[a][0] for a in combo]
            if max(sites.count(s) for s in set(sites)) > 2:
                continue
            sets.append(tuple(sorted(combo)))
    return sets


def solve(target_core: int, seed: int = 0, iters: int = 400000):
    """Случайный рестарт + жадное улучшение. Пространство маленькое, этого хватает."""
    global pool
    pool = {}
    rng = random.Random(seed)
    cap0 = capacity()
    fx = fixed_links()

    # ВАЖНО: ссылки готовых статей уже записаны в PLACEMENTS-LOG, то есть уже сидят
    # в PRIOR и вычтены в capacity(). Второй раз их вычитать нельзя.
    cap_after_fixed = dict(cap0)
    for _, a in fx:
        assert cap_after_fixed[a] >= 0, f'готовая статья превышает квоту №{a}'

    fixed_e = sum(1 for _, a in fx if ACCEPTORS[a][0] == 'enger')
    fixed_p = len(fx) - fixed_e

    need_e = round(target_core * TARGET_RATIO[0]) - fixed_e
    need_p = round(target_core * TARGET_RATIO[1]) - fixed_p
    if need_e < 0 or need_p < 0:
        return None, f'цель {target_core} недостижима: готовые статьи уже дают {fixed_e}E/{fixed_p}P'

    options = {d.domain: enumerate_sets(d, cap_after_fixed, MAX_LINKS) for d in FREE}
    for dom, o in options.items():
        if not o:
            return None, f'{dom}: нет допустимых акцепторов'

    best = None
    for _ in range(iters):
        cap = dict(cap_after_fixed)
        pick, ok = {}, True
        for d in rng.sample(FREE, len(FREE)):
            avail = [s for s in options[d.domain] if all(cap[a] > 0 for a in s)]
            if not avail:
                ok = False
                break
            s = rng.choice(avail)
            for a in s:
                cap[a] -= 1
            pick[d.domain] = s
        if not ok:
            continue

        e = sum(1 for s in pick.values() for a in s if ACCEPTORS[a][0] == 'enger')
        p = sum(len(s) for s in pick.values()) - e
        if (e, p) != (need_e, need_p):
            continue

        # дилеры: каждому донору столько слотов, сколько осталось до MAX_LINKS
        slots = {d.domain: MAX_LINKS - len(pick[d.domain]) for d in FREE}
        deal = assign_dealers(slots)
        if deal is None:
            continue

        score = sum(d.fit(a) for d in FREE for a in pick[d.domain])
        score += sum(next(x for x in DONORS if x.domain == dom).dealers.get(k, 0)
                     for dom, ks in deal.items() for k in ks)
        # мягкий штраф за статьи с 3 ссылками (след заметнее)
        score -= 1.2 * sum(1 for dom in pick
                           if len(pick[dom]) + len(deal.get(dom, [])) == 3)
        key = tuple(sorted((dom, tuple(s)) for dom, s in pick.items()))
        prev = pool.get(key)
        if prev is None or score > prev[0]:
            pool[key] = (score, pick, deal)
        if best is None or score > best[0]:
            best = (score, pick, deal)

    if best is None:
        return None, f'решения для {target_core} core-ссылок не найдено'
    return best, None


def alternatives(target_core: int, n: int = 6):
    """Раскладки, которые прошли все ограничения, но уступили победителю по фиту.

    Владелец просил показать «те, что в выбор не попали, но были близки» — без них
    невозможно понять, насколько выбор устойчив и что теряется при замене.
    """
    ranked = sorted(pool.values(), key=lambda x: -x[0])
    return ranked[1:n + 1]


def diff_vs(best, alt):
    """Чем альтернатива отличается от победителя — по донорам."""
    _, pb, db = best
    _, pa, da = alt
    out = []
    for dom in pb:
        cb, ca = set(pb[dom]), set(pa[dom])
        kb, ka = set(db.get(dom, [])), set(da.get(dom, []))
        if cb != ca or kb != ka:
            out.append({
                'donor': dom,
                'was': {'core': sorted(cb), 'dealers': sorted(kb)},
                'alt': {'core': sorted(ca), 'dealers': sorted(ka)},
            })
    return out


def assign_dealers(slots: dict):
    """Каждый дилерский домен минимум 1 раз, в донора с ненулевым фитом."""
    by_domain = {d.domain: d for d in DONORS}
    order = sorted(DEALERS, key=lambda k: sum(
        1 for dom in slots if k in by_domain[dom].dealers))     # редкие — первыми
    res = {dom: [] for dom in slots}
    free = dict(slots)

    def rec(i: int) -> bool:
        if i == len(order):
            return True
        k = order[i]
        cands = sorted((dom for dom in slots if free[dom] > 0 and k in by_domain[dom].dealers),
                       key=lambda dom: -by_domain[dom].dealers[k])
        for dom in cands:
            res[dom].append(k)
            free[dom] -= 1
            if rec(i + 1):
                return True
            res[dom].pop()
            free[dom] += 1
        return False

    return res if rec(0) else None


def report(best, target_core: int) -> dict:
    score, pick, deal = best
    by_domain = {d.domain: d for d in DONORS}
    rows, used = [], {}

    for d in DONORS:
        if d.fixed is not None:
            core, dl = list(d.fixed), []
        else:
            core, dl = list(pick[d.domain]), deal.get(d.domain, [])
        for a in core:
            used[a] = used.get(a, 0) + 1
        rows.append({
            'prio': d.prio, 'donor': d.domain, 'profile': d.profile,
            'core': [{'n': a, 'site': ACCEPTORS[a][0], 'url': ACCEPTORS[a][1],
                      'segment': ACCEPTORS[a][3], 'fit': d.fit(a),
                      'from_matrix': a in d.base} for a in core],
            'dealers': [{'key': k, 'url': DEALERS[k][0], 'segment': DEALERS[k][1]} for k in dl],
            'links': len(core) + len(dl),
            'ready': d.fixed is not None, 'article': d.article, 'note': d.note,
        })

    e = sum(1 for r in rows for c in r['core'] if c['site'] == 'enger')
    p = sum(1 for r in rows for c in r['core'] if c['site'] == 'prokom')
    return {
        'target_core': target_core, 'score': round(score, 1),
        'links_total': sum(r['links'] for r in rows),
        'core_total': e + p, 'enger': e, 'prokom': p,
        'ratio': f'{e / (e + p):.0%} / {p / (e + p):.0%}',
        'dealers_covered': sorted({k for r in rows for k in [x['key'] for x in r['dealers']]}),
        'acceptor_usage': {a: {'used_month': used.get(a, 0), 'prior': PRIOR.get(a, 0),
                               'quota': ACCEPTORS[a][2]} for a in sorted(ACCEPTORS)},
        'rows': rows,
    }


def validate(plan: dict) -> list:
    """Независимая проверка результата — не доверяем солверу на слово."""
    errs = []
    for a, u in plan['acceptor_usage'].items():
        # used_month включает ссылки готовых статей, которые уже сидят в PRIOR —
        # чтобы не считать их дважды, вычитаем.
        real = u['prior'] + u['used_month'] - _fixed_hits(plan, a)
        if real > u['quota']:
            errs.append(f'№{a}: {real} ссылок при квоте {u["quota"]}')
    for r in plan['rows']:
        if not MIN_LINKS <= r['links'] <= MAX_LINKS:
            errs.append(f'{r["donor"]}: {r["links"]} ссылок (допустимо {MIN_LINKS}-{MAX_LINKS})')
        if not r['core']:
            errs.append(f'{r["donor"]}: нет ни одной ссылки на ядро')
    if len(plan['dealers_covered']) != len(DEALERS):
        errs.append(f'дилеры покрыты не все: {plan["dealers_covered"]}')
    e, p = plan['enger'], plan['prokom']
    if round(e / (e + p), 2) != TARGET_RATIO[0]:
        errs.append(f'доля Enger {e / (e + p):.0%} вместо {TARGET_RATIO[0]:.0%}')
    return errs


def _fixed_hits(plan: dict, a: int) -> int:
    return sum(1 for r in plan['rows'] if r['ready'] for c in r['core'] if c['n'] == a)


def _month_reuses(plan: dict, a: int) -> bool:
    return _fixed_hits(plan, a) > 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('-o', '--out', default='month-plan.json')
    ap.add_argument('--core', type=int, default=15, help='сколько ссылок на ядро за месяц')
    ap.add_argument('--seed', type=int, default=7)
    ap.add_argument('--iters', type=int, default=400000)
    ap.add_argument('--alts', type=int, default=6, help='сколько близких альтернатив показать')
    args = ap.parse_args()

    best, err = solve(args.core, args.seed, args.iters)
    if err:
        print('НЕ РЕШЕНО:', err)
        return 1

    plan = report(best, args.core)
    errs = validate(plan)

    print(f'core {plan["core_total"]} (Enger {plan["enger"]} / ProKompressor {plan["prokom"]}'
          f' = {plan["ratio"]}), всего ссылок {plan["links_total"]}, '
          f'дилеры {len(plan["dealers_covered"])}/{len(DEALERS)}, фит-балл {plan["score"]}')
    print()
    for r in sorted(plan['rows'], key=lambda x: x['prio']):
        tag = ' [готова]' if r['ready'] else ''
        core = ', '.join(f'№{c["n"]} {c["segment"]}' + ('' if c['from_matrix'] else ' (вне матрицы)')
                         for c in r['core'])
        dl = ', '.join(x['key'] for x in r['dealers'])
        print(f'{r["prio"]:>2}. {r["donor"]:<22}{tag}')
        print(f'    ядро:   {core}')
        if dl:
            print(f'    дилеры: {dl}')
    print()
    print('ПРОВЕРКА:', 'ошибок нет' if not errs else '')
    for e in errs:
        print('  ✗', e)

    alts = alternatives(args.core, args.alts)
    plan['alternatives'] = []
    print(f'\nПОЧТИ ПРОШЛИ ({len(alts)} шт., все проходят те же жёсткие ограничения):')
    for i, alt in enumerate(alts, 1):
        d = diff_vs(best, alt)
        rec = {'rank': i, 'score': round(alt[0], 1),
               'delta': round(alt[0] - best[0], 1), 'diff': d,
               'plan': report(alt, args.core)}
        rec['validation'] = validate(rec['plan'])
        plan['alternatives'].append(rec)
        print(f'  A{i}: фит {alt[0]:.1f} ({alt[0] - best[0]:+.1f}), отличий по донорам: {len(d)}')
        for x in d:
            was = ', '.join(f'№{n}' for n in x['was']['core']) + \
                  (' + ' + '/'.join(x['was']['dealers']) if x['was']['dealers'] else '')
            now = ', '.join(f'№{n}' for n in x['alt']['core']) + \
                  (' + ' + '/'.join(x['alt']['dealers']) if x['alt']['dealers'] else '')
            print(f'      {x["donor"]:<22} {was}  ->  {now}')

    plan['validation'] = errs
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    print(f'\n-> {args.out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
