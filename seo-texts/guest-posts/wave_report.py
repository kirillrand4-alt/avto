#!/usr/bin/env python3
"""Итоговый отчёт по волне: что готово, что требует взгляда, чем отличаются прогоны.

Собирается в конце ночного конвейера (`pipeline.sh`). Показывает не только «сколько
принято», но и сравнение двух прогонов — до и после шпаргалки опорных величин: ради
неё всё и переделывалось, и её эффект должен быть виден числом, а не на слово.
"""
import glob, json, os, re

OUT = 'WAVE-REPORT.md'


def parse_log(path):
    t = open(path, encoding='utf-8').read()
    slug = os.path.basename(path).replace('gp-', '').replace('.finalize-log.md', '')
    g = lambda rx, d=None: (re.search(rx, t) or [None, d])[1] if re.search(rx, t) else d
    place = re.findall(r'место (\d+)/10, релевантность (\d+)/10', t)
    fails = re.findall(r'- \[([a-z_]+)\] вердикт: FAIL', t)
    return {
        'slug': slug,
        'ok': 'ГОТОВ К ПУБЛИКАЦИИ' in t,
        'edits': int(g(r'Правок применено: (\d+)', 0) or 0),
        'conflicts': t.count('КОНФЛИКТ ПРАВОК'),
        'place': int(place[0][0]) if place else None,
        'relevance': int(place[0][1]) if place else None,
        'fail_lenses': sorted(set(fails)),
        'dimension': 'FAIL' if '[teh_razmernost] вердикт: FAIL' in t else
                     ('PASS' if 'teh_razmernost' in t else '—'),
        'not_found': t.count('НЕ НАЙДЕНА цитата'),
    }


def main():
    jobs = {j['slug']: j for j in
            (json.loads(l) for l in open('final-jobs.jsonl', encoding='utf-8') if l.strip())}
    rows = [parse_log(p) for p in sorted(glob.glob('ready/*.finalize-log.md'))]
    rows = [r for r in rows if r['slug'] in jobs]
    before = {}
    if os.path.exists('accept1-stat.json'):
        before = {r['slug']: r for r in json.load(open('accept1-stat.json', encoding='utf-8'))}

    ok = [r for r in rows if r['ok']]
    bad = [r for r in rows if not r['ok']]
    dim_fail = [r for r in rows if r['dimension'] == 'FAIL']
    dim_fail_before = [s for s, r in before.items() if str(r.get('dim', '')).startswith('FAIL')]

    lines = [f'# Волна 2: итог приёмки ({len(ok)} из {len(rows)} готовы)', '']
    lines += ['## Сравнение прогонов', '',
              'Первый прогон — статьи без шпаргалки опорных величин, второй — с ней.',
              'Разница по линзе размерностей показывает, окупилась ли шпаргалка.', '',
              f'* линза `teh_razmernost` дала FAIL: **{len(dim_fail_before)} статей до шпаргалки, '
              f'{len(dim_fail)} после**',
              f'* принято без ручного взгляда: {len(ok)} из {len(rows)}',
              f'* суммарно правок применено: {sum(r["edits"] for r in rows)}',
              f'* конфликтов правок: {sum(r["conflicts"] for r in rows)}', '']

    lines += ['## Статьи', '',
              '| Статья | Донор | Итог | Правок | Место | Релев. | Размерности | Не сошлись |',
              '|---|---|---|---|---|---|---|---|']
    for r in sorted(rows, key=lambda x: (not x['ok'], x['slug'])):
        j = jobs[r['slug']]
        lines.append('| %s | %s | %s | %d | %s | %s | %s | %s |' % (
            r['slug'][:34], j['donor'], '✅' if r['ok'] else '⚠️ ручной взгляд',
            r['edits'], r['place'] or '—', r['relevance'] or '—', r['dimension'],
            ', '.join(r['fail_lenses']) or '—'))

    if bad:
        lines += ['', '## Требуют ручного взгляда', '']
        for r in bad:
            j = jobs[r['slug']]
            lines.append(f"**{j['donor']}** — {j.get('title', '')}")
            lines.append(f"  не сошлись: {', '.join(r['fail_lenses']) or '—'}; "
                         f"конфликтов правок: {r['conflicts']}; "
                         f"ненайденных цитат: {r['not_found']}")
            lines.append(f"  лог: `ready/gp-{r['slug']}.finalize-log.md`")
            lines.append('')

    if os.path.exists('series-check.json'):
        sc = json.load(open('series-check.json', encoding='utf-8'))
        lines += ['## Проверка серии', '',
                  f"вердикт: {sc.get('verdict', '?')}",
                  f"общие приёмы: {(sc.get('common') or '—')[:400]}",
                  f"статей с замечаниями: {len(sc.get('problems') or [])}", '']

    lines += ['## Что дальше', '',
              '1. Прочитать глазами статьи из раздела «требуют ручного взгляда».',
              '2. Пары «донор → страница» и якоря зафиксированы в `final-jobs.jsonl`.',
              '3. Перед закупкой: запись в `PLACEMENTS-LOG.md`, затем ОК владельца.',
              '   Отправка на площадку — действие вовне, само по себе не выполняется.']
    open(OUT, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    print(f'{OUT}: готовых {len(ok)} из {len(rows)}, '
          f'размерности FAIL {len(dim_fail_before)} -> {len(dim_fail)}')


if __name__ == '__main__':
    main()
