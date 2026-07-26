# -*- coding: utf-8 -*-
"""Сборка статистики и search-problems.csv из результатов прогона + оценок аудитора.
Воспроизводит формат v2: строки с relevance<2, CSV utf-8-sig, ';', топ-3 имени по 45 символов."""
import csv, json
from collections import Counter

recs = {r['phrase']: r for l in open('inventory/search-results.jsonl')
        for r in [json.loads(l)]}
ev = json.load(open('inventory/search-eval.json'))

# --- общая статистика (формат сводки v2) ---
c = Counter(e['relevance'] for e in ev)
n = len(ev)
print(f'оценено: {n}')
print(f'точных (2): {c[2]} = {c[2]/n:.0%} | частичных (1): {c[1]} = {c[1]/n:.0%} | '
      f'плохих/пустых (0): {c[0]} = {c[0]/n:.0%}')
for src in ('site', 'webmaster'):
    xs = [e['relevance'] for e in ev if recs.get(e['phrase'], {}).get('source') == src]
    print(f'средняя релевантность {src}: {sum(xs)/len(xs):.2f} из 2 ({len(xs)} фраз)')
print('fail_type:', Counter(e['fail_type'] for e in ev).most_common())

# --- проблемные строки ---
with open('inventory/search-problems.csv', 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f, delimiter=';')
    w.writerow(['Запрос', 'Тип провала', 'Релевантность/2', 'Источник', 'Нашлось',
                'Что не так', 'Топ-3 выдачи'])
    bad = 0
    for e in ev:
        if e['relevance'] >= 2:
            continue
        r = recs.get(e['phrase'], {})
        top = ' | '.join(t['name'][:45] for t in r.get('top', [])[:3])
        w.writerow([e['phrase'], e['fail_type'], e['relevance'], r.get('source', '?'),
                    r.get('found', 0), e['note'], top])
        bad += 1
print('строк в search-problems.csv:', bad)
