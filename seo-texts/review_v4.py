# -*- coding: utf-8 -*-
"""Независимая рецензия отчёта v3 через провайдерский API (аналог review_search_report.py).
Рецензент проверяет: подтверждаются ли выводы данными, корректна ли статистика по 176 живым
фразам, не преувеличены ли «регрессы» (оценщик мог судить иначе даже при изменившемся топе)."""
import csv, json, re

from gen_provider import make_client, call

report = open('inventory/OTCHET-poisk-v4.md').read()
ev2 = {e['phrase']: e for e in json.load(open('inventory/search-eval-v3.json'))}
ev3 = {e['phrase']: e for e in json.load(open('inventory/search-eval.json'))}
rs2 = {r['phrase']: r for l in open('inventory/search-results-v3.jsonl') for r in [json.loads(l)]}
rs3 = {r['phrase']: r for l in open('inventory/search-results.jsonl') for r in [json.loads(l)]}

def row(p):
    return {'phrase': p, 'src': rs3[p].get('source'),
            'rel': [ev2[p]['relevance'], ev3[p]['relevance']],
            'found': [rs2[p].get('found'), rs3[p].get('found')],
            'top3_v2': [t['name'][:50] for t in rs2[p].get('top', [])[:2]],
            'top3_v3': [t['name'][:50] for t in rs3[p].get('top', [])[:2]],
            'note_v3': ev3[p]['note']}

regr = sorted((p for p in ev2 if p in ev3 and ev3[p]['relevance'] < ev2[p]['relevance']))
regr = sorted(regr, key=lambda p: ev3[p]['relevance'] - ev2[p]['relevance'])[:40]  # 40 самых глубоких падений
fixed = sorted((p for p in ev2 if p in ev3 and ev3[p]['relevance'] > ev2[p]['relevance']))
site_all = [p for p in ev3 if rs3[p].get('source') == 'site']

PROMPT = f"""Ты - строгий рецензент аналитических отчётов. Ниже отчёт v4 о втором контрольном
прогоне внутреннего поиска магазина промышленных компрессоров (после починки поиска
разработчиком), воспроизводящий методику v3/v4. Твоя задача - найти слабые места ДО того,
как отчёт уйдёт владельцу и разработчику Битрикса.

=== ОТЧЁТ V3 (проверяемый) ===
{report}

=== ДАННЫЕ ДЛЯ ПРОВЕРКИ ===
60 самых глубоких ухудшений оценки (из 242) (v3->v4), с топами до/после (JSON):
{json.dumps([row(p) for p in regr], ensure_ascii=False)}

Случайные 12 фраз с улучшением:
{json.dumps([row(p) for p in fixed[::max(1, len(fixed)//12)][:12]], ensure_ascii=False)}

Сводка по 176 живым фразам: лучше 18, хуже 32, среднее 1.73 -> 1.66 (списка нет для краткости).

Проверь и ответь СТРОГО ОДНИМ JSON-объектом без преамбул и markdown (первый символ - открывающая
фигурная скобка):
{{"claims": [{{"claim": "краткая формулировка утверждения отчёта", "verdict": "подтверждён/подтверждён частично/не подтверждён", "reasoning": "..."}}],
 "stat_significance": "честная оценка: просадка живых фраз 1.73->1.66 при 18 лучше / 32 хуже из 176 - это уверенный вывод или в пределах разброса ИИ-оценщика между прогонами? учти, что оценщик тот же, но недетерминированный",
 "overstatements": ["места, где отчёт сильнее данных"],
 "understatements": ["важное из данных, что отчёт упустил"],
 "report_edits": ["конкретные правки"],
 "overall": "вердикт: годен ли отчёт к отправке после правок"}}"""

import sys, time
import gen_provider as gp
text = ''
for attempt in range(5):
    if attempt:
        time.sleep(20 * attempt)
    try:
        msg = gp._raw_stream([{'role': 'user', 'content': PROMPT}], 'claude-fable-5', 16000, thinking=False)
    except Exception as ex:
        print('сбой', repr(ex)[:120], file=sys.stderr); continue
    text = ''.join(b.text for b in msg.content if b.type == 'text').strip()
    if len(text) > 500:
        break
    print('пустой ответ, попытка', attempt + 1, file=sys.stderr)
open('inventory/report-v4-review-raw.txt', 'w').write(text)
m = re.search(r'\{.*\}', text, re.S)
rev = json.loads(m.group(0))
json.dump(rev, open('inventory/report-v4-review.json', 'w'), ensure_ascii=False, indent=1)
print(json.dumps(rev, ensure_ascii=False, indent=1))
