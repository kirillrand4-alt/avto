# -*- coding: utf-8 -*-
"""Сухой прогон email-ассистента: 14 синтетических писем по типам плейбука ->
черновики -> скептик-оценка. Выход: DRYRUN-REPORT.md"""
import json, os, sys
DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(DIR))
import gen_provider as gp
from email_answer import answer

client = gp.make_client()

# 1) синтетические письма (реалистичные, по типам, с подвохами)
msg = gp.call(client, [{'role': 'user', 'content':
    'Сгенерируй 14 реалистичных писем от B2B-клиентов поставщику промышленных компрессоров '
    '(prokompressor.ru). Распределение: 3 запроса цены конкретных моделей (бренды Enger, Berg, Remeza; '
    'одна модель с опечаткой), 3 подбора по задаче (автосервис, пищевое производство с азотом, стройка), '
    '2 наличие/сроки, 2 торга («дайте скидку»), 1 рекламация, 1 запрос каталога, 1 нецелевое (реклама SEO-услуг), '
    '1 сложное (просят модель, снятую с производства). Пиши как реальные люди: кратко, с ошибками, '
    'иногда без приветствия. Верни ТОЛЬКО JSON [{"n":1,"expected_type":N,"letter":"..."}]'}],
    model='claude-fable-5', effort='medium')
letters = gp.parse_json(msg)
json.dump(letters, open(os.path.join(DIR, 'dryrun-letters.json'), 'w'), ensure_ascii=False, indent=1)
print(f'писем: {len(letters)}', flush=True)

# 2) черновики
results = []
for L in letters:
    try:
        r = answer(L['letter'], client)
    except Exception as e:
        r = {'error': repr(e)[:150]}
    r['n'], r['expected_type'], r['letter'] = L['n'], L['expected_type'], L['letter']
    results.append(r)
    print(f"  #{L['n']} тип {r.get('type')}/{L['expected_type']} esc={r.get('escalate')} "
          f"qa={len(r.get('qa_issues', []))}", flush=True)
json.dump(results, open(os.path.join(DIR, 'dryrun-results.json'), 'w'), ensure_ascii=False, indent=1)

# 3) скептик
msg = gp.call(client, [{'role': 'user', 'content':
    'Ты скептичный руководитель отдела продаж компрессорного дистрибьютора. Оцени черновики '
    'ответов ассистента (письмо клиента -> черновик). Критерии: не выдумал ли цифры/модели, '
    'правильно ли эскалировал торг/рекламации, тон, следующий шаг, «отправил бы без правок?». '
    'Верни ТОЛЬКО JSON {"per_letter": [{"n":N,"send_as_is":true/false,"problems":["..."]}], '
    '"summary":"...", "ready_percent":N}\n\n' +
    json.dumps([{k: r.get(k) for k in ('n', 'letter', 'type', 'escalate', 'draft', 'qa_issues')}
                for r in results], ensure_ascii=False)}],
    model='claude-fable-5', effort='high')
rev = gp.parse_json(msg)
json.dump(rev, open(os.path.join(DIR, 'dryrun-review.json'), 'w'), ensure_ascii=False, indent=1)

ok = sum(1 for p in rev.get('per_letter', []) if p.get('send_as_is'))
lines = [f"# Сухой прогон email-ассистента\n",
         f"- Писем: {len(results)}; тип угадан: "
         f"{sum(1 for r in results if r.get('type') == r.get('expected_type'))}/{len(results)}",
         f"- «Отправил бы без правок»: {ok}/{len(rev.get('per_letter', []))} ({rev.get('ready_percent')}%)",
         f"- Вердикт скептика: {rev.get('summary', '')}\n"]
for p in rev.get('per_letter', []):
    if not p.get('send_as_is'):
        lines.append(f"- #{p['n']}: " + '; '.join(p.get('problems', []))[:200])
open(os.path.join(DIR, 'DRYRUN-REPORT.md'), 'w').write('\n'.join(lines))
print('=== DRYRUN ГОТОВ ===', flush=True)
