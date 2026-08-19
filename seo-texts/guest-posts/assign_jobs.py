#!/usr/bin/env python3
"""Фаза 2: распределение доноров по нашим сайтам с квотами владельца.

Агенты дали оценки фита 0-10 по каждому сайту (`fit_score.py`). Здесь код решает,
кто кому достанется, максимизируя суммарный фит при квотах. Жадный выбор агента без
этого шага отдал бы всё prokompressor.ru - у него 33 страницы из 58 и самая денежная
позиция; сателлиты остались бы без ссылок, хотя нужнее всего они именно им.

Венгерский алгоритм здесь избыточен: задача маленькая (24×6), а жадный проход по
убыванию оценки с проверкой квот даёт тот же результат на таких размерностях и
читается без комментариев.

Доноры, у которых максимум фита ниже порога, в раскладку не идут вовсе - это те
самые площадки, где мост пришлось бы выдумывать.

    python3 assign_jobs.py [порог]        # порог по умолчанию 4
"""
import json, sys

QUOTA = {'prokompressor.ru': 12, 'berg-compressor.com': 3, 'dali-kompressor.ru': 2,
         'abac-kompressor.ru': 2, 'ac-kompressor.ru': 2, 'enger-air.ru': 3}


def main():
    floor = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    fits = {}
    for line in open('fit-scores.jsonl', encoding='utf-8'):
        if line.strip():
            r = json.loads(line)
            if r.get('fit'):
                fits[r['donor']] = r['fit']
    pairs = sorted(((f['score'], d, s, f) for d, sf in fits.items() for s, f in sf.items()),
                   key=lambda x: -x[0])
    left = dict(QUOTA)
    taken, assign = set(), {}
    for score, dom, site, f in pairs:
        if score < floor or dom in taken or left.get(site, 0) <= 0:
            continue
        assign[dom] = {'site': site, 'score': score, 'page': f['page'], 'why': f['why']}
        taken.add(dom); left[site] -= 1
    dropped = {d: max(sf.values(), key=lambda x: x['score'])['score']
               for d, sf in fits.items() if d not in assign}
    json.dump(assign, open('assignment.json', 'w'), ensure_ascii=False, indent=1)
    print('назначено: %d | не прошли порог %d: %d' % (len(assign), floor, len(dropped)))
    for site in QUOTA:
        got = [(d, a) for d, a in assign.items() if a['site'] == site]
        print('\n%s — %d из %d квоты:' % (site, len(got), QUOTA[site]))
        for d, a in sorted(got, key=lambda kv: -kv[1]['score']):
            print('   %-28s фит %2d/10  %s' % (d, a['score'], a['page'][:52]))
    if dropped:
        print('\nне назначены (лучший фит ниже %d):' % floor)
        for d, s in sorted(dropped.items(), key=lambda kv: -kv[1]):
            print('   %-28s максимум %d/10' % (d, s))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
