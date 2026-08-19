#!/usr/bin/env python3
"""Фаза 2: распределение доноров по нашим сайтам с квотами владельца.

Агенты дали оценки фита 0-10 по каждому сайту (`fit_score.py`). Здесь код решает,
кто кому достанется. Квоты - решение владельца: качаем основной сайт и сателлиты,
enger-air.ru в этой волне не первый.

**Почему не жадный проход по убыванию оценки.** Первая реализация раздавала пары
в порядке убывания фита - и сателлиты остались с нулём: prokompressor.ru забрал
mplast.by и koch-market.ru (по 9/10), хотя те предназначались abac и dali. Это та же
ловушка, от которой квоты и защищают: у главного сайта 33 страницы из 58, он выигрывает
почти любое сравнение, и «лучшая пара» глобально всегда его.

Здесь аукционная логика: пару выбираем не по величине фита, а по УПУЩЕННОЙ ВЫГОДЕ -
насколько сайт потеряет, если этот донор уйдёт к другому. Донор, который хорош только
для dali-kompressor.ru, достанется dali, даже если prokompressor оценил его выше.

Дополнительно: не больше MAX_PER_PAGE доноров на одну страницу - иначе три ссылки
приезжают на один URL и упираются в лимит темпа (одна ссылка на URL в две недели).

    python3 assign_jobs.py [порог]        # порог по умолчанию 4
"""
import json, sys

QUOTA = {'prokompressor.ru': 12, 'berg-compressor.com': 3, 'dali-kompressor.ru': 2,
         'abac-kompressor.ru': 2, 'ac-kompressor.ru': 2, 'enger-air.ru': 3}
MAX_PER_PAGE = 2

# Приоритет владельца: качаем основной сайт и сателлиты, enger-air.ru в этой волне
# не первый. Без этой поправки аукцион отдавал лучших доноров enger - у него малая
# квота, а значит высокая упущенная выгода на каждой паре.
BONUS = {'prokompressor.ru': 3, 'berg-compressor.com': 1, 'dali-kompressor.ru': 1,
         'abac-kompressor.ru': 1, 'ac-kompressor.ru': 1, 'enger-air.ru': 0}

# Оценки модели шумные: два независимых прогона разошлись (metallicheckiy-portal.ru
# получил 9/10 на prokompressor в первом и 10/10 на enger во втором). Усредняем все
# доступные замеры - среднее двух прогонов устойчивее любого одного.
SOURCES = ['fit-scores.jsonl', 'fit-scores2.jsonl', 'fit-scores3.jsonl']


def main():
    floor = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    import os
    acc = {}
    for src in SOURCES:
        if not os.path.exists(src):
            continue
        for line in open(src, encoding='utf-8'):
            if not line.strip():
                continue
            r = json.loads(line)
            for site, f in (r.get('fit') or {}).items():
                acc.setdefault(r['donor'], {}).setdefault(site, []).append(f)
    fits = {}
    for dom, sites in acc.items():
        row = {}
        for site, lst in sites.items():
            avg = sum(x['score'] for x in lst) / len(lst)
            best = max(lst, key=lambda x: x['score'])
            if avg + BONUS.get(site, 0) >= floor:
                row[site] = {'score': round(avg, 1), 'runs': len(lst), 'page': best['page'],
                             'why': best['why'], 'rank': avg + BONUS.get(site, 0)}
        if row:
            fits[dom] = row

    left = dict(QUOTA)
    per_page = {}
    assign = {}
    free = set(fits)
    while free:
        best = None                                          # (упущенная выгода, фит, донор, сайт)
        for site, quota in left.items():
            if quota <= 0:
                continue
            cands = sorted(((f[site]['rank'], d) for d, f in fits.items()
                            if d in free and site in f
                            and per_page.get((site, f[site]['page']), 0) < MAX_PER_PAGE),
                           reverse=True)
            if not cands:
                continue
            top, second = cands[0], (cands[1] if len(cands) > 1 else (0, None))
            regret = top[0] - second[0]                      # потеря сайта, если донор уйдёт
            key = (regret, top[0])
            if best is None or key > best[0]:
                best = (key, top[1], site)
        if best is None:
            break
        _, dom, site = best
        f = fits[dom][site]
        assign[dom] = {'site': site, 'score': f['score'], 'runs': f.get('runs', 1),
                       'page': f['page'], 'why': f['why']}
        free.discard(dom); left[site] -= 1
        per_page[(site, f['page'])] = per_page.get((site, f['page']), 0) + 1

    dropped = {d: max(round(sum(x['score'] for x in lst) / len(lst), 1)
                      for lst in sites.values())
               for d, sites in acc.items() if d not in assign}
    json.dump(assign, open('assignment.json', 'w'), ensure_ascii=False, indent=1)
    print('назначено: %d | без назначения: %d (порог фита %d)' % (len(assign), len(dropped), floor))
    for site in QUOTA:
        got = [(d, a) for d, a in assign.items() if a['site'] == site]
        print('\n%s — %d из %d квоты:' % (site, len(got), QUOTA[site]))
        for d, a in sorted(got, key=lambda kv: -kv[1]['score']):
            print('   %-28s фит %4.1f/10 (замеров %d)  %s' % (
                d, a['score'], a.get('runs', 1), a['page'][:52]))
    if dropped:
        print('\nбез назначения:')
        for d, s in sorted(dropped.items(), key=lambda kv: -kv[1]):
            print('   %-28s лучший средний фит %.1f/10' % (d, s))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
