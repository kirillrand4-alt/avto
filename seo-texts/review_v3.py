# -*- coding: utf-8 -*-
"""Независимая рецензия отчёта v3 через провайдерский API (аналог review_search_report.py).
Рецензент проверяет: подтверждаются ли выводы данными, корректна ли статистика по 176 живым
фразам, не преувеличены ли «регрессы» (оценщик мог судить иначе даже при изменившемся топе)."""
import csv, json, re

from gen_provider import make_client, call

report = open('inventory/OTCHET-poisk-v3.md').read()
ev2 = {e['phrase']: e for e in json.load(open('inventory/search-eval-v2.json'))}
ev3 = {e['phrase']: e for e in json.load(open('inventory/search-eval.json'))}
rs2 = {r['phrase']: r for l in open('inventory/search-results-v2.jsonl') for r in [json.loads(l)]}
rs3 = {r['phrase']: r for l in open('inventory/search-results.jsonl') for r in [json.loads(l)]}

def row(p):
    return {'phrase': p, 'src': rs3[p].get('source'),
            'rel': [ev2[p]['relevance'], ev3[p]['relevance']],
            'found': [rs2[p].get('found'), rs3[p].get('found')],
            'top3_v2': [t['name'][:70] for t in rs2[p].get('top', [])[:3]],
            'top3_v3': [t['name'][:70] for t in rs3[p].get('top', [])[:3]],
            'note_v3': ev3[p]['note']}

regr = sorted((p for p in ev2 if p in ev3 and ev3[p]['relevance'] < ev2[p]['relevance']))
fixed = sorted((p for p in ev2 if p in ev3 and ev3[p]['relevance'] > ev2[p]['relevance']))
site_all = [p for p in ev3 if rs3[p].get('source') == 'site']

PROMPT = f"""Ты - строгий рецензент аналитических отчётов. Ниже отчёт v3 о контрольном
прогоне внутреннего поиска магазина промышленных компрессоров (после починки поиска
разработчиком), воспроизводящий методику v2. Твоя задача - найти слабые места ДО того,
как отчёт уйдёт владельцу и разработчику Битрикса.

=== ОТЧЁТ V3 (проверяемый) ===
{report}

=== ДАННЫЕ ДЛЯ ПРОВЕРКИ ===
Все фразы с ухудшением оценки (v2->v3), с топами до/после (JSON):
{json.dumps([row(p) for p in regr], ensure_ascii=False)}

Случайные 25 фраз с улучшением:
{json.dumps([row(p) for p in fixed[::max(1, len(fixed)//25)][:25]], ensure_ascii=False)}

Все 176 живых внутренних фраз с оценками v2/v3:
{json.dumps([{'phrase': p, 'rel': [ev2[p]['relevance'], ev3[p]['relevance']]} for p in sorted(site_all)], ensure_ascii=False)}

Проверь и ответь СТРОГО ОДНИМ JSON-объектом без преамбул и markdown (первый символ - открывающая
фигурная скобка):
{{"claims": [{{"claim": "краткая формулировка утверждения отчёта", "verdict": "подтверждён/подтверждён частично/не подтверждён", "reasoning": "..."}}],
 "stat_significance": "честная оценка: просадка живых фраз 1.80->1.73 при 15 лучше / 23 хуже из 176 - это уверенный вывод или в пределах разброса ИИ-оценщика между прогонами? учти, что оценщик тот же, но недетерминированный",
 "overstatements": ["места, где отчёт сильнее данных"],
 "understatements": ["важное из данных, что отчёт упустил"],
 "report_edits": ["конкретные правки"],
 "overall": "вердикт: годен ли отчёт к отправке после правок"}}"""

client = make_client()
msg = call(client, [{'role': 'user', 'content': PROMPT}], 'claude-fable-5')
text = ''.join(b.text for b in msg.content if b.type == 'text')
open('inventory/report-v3-review-raw.txt', 'w').write(text)
m = re.search(r'\{.*\}', text, re.S)
rev = json.loads(m.group(0))
json.dump(rev, open('inventory/report-v3-review.json', 'w'), ensure_ascii=False, indent=1)
print(json.dumps(rev, ensure_ascii=False, indent=1))
