# -*- coding: utf-8 -*-
"""Adversarial-верификация зависимостей: сверка каждого правила с сырыми строками листа прайса."""
import json, re
from concurrent.futures import ThreadPoolExecutor, as_completed
from gen_provider import make_client, call

tasks = json.load(open('kb/dep-verify-tasks.json'))

PROMPT = """Ты ПРОВЕРЯЮЩИЙ. Ранее ИИ извлёк из этого листа прайса «зависимости» (правила вида
«параметр зависит от мощности/серии»). Некоторые правила — АРТЕФАКТЫ (ИИ принял заголовок-раздел
за признак модели, или обобщил по одному примеру). Твоя задача — проверить КАЖДОЕ правило по
сырым строкам и вынести вердикт.

Лист: «{sheet}»
СЫРЫЕ СТРОКИ (массив массивов ячеек, шапки + модели):
{rows}

ПРАВИЛА НА ПРОВЕРКУ:
{deps}

Для КАЖДОГО правила верни объект:
- rule: краткая суть правила
- verdict: confirmed (данные явно подтверждают на нескольких моделях) / artifact (не подтверждается,
  ошибка извлечения) / nuanced (частично верно, нужна поправка)
- evidence: конкретные модели/значения из строк, подтверждающие или опровергающие
- corrected: если nuanced/artifact — как правильно (или "удалить")

Особое внимание: правила «X только при мощности Y» — проверь, нет ли моделей с X при ДРУГИХ мощностях.
Ответь ОДНИМ JSON: {{"sheet":"{sheet}","checks":[...]}}"""

client = make_client()
def worker(t):
    d = json.load(open(t['file']))
    rows = d['rows'][:130]
    deps = t['deps'] if isinstance(t['deps'], list) else [t['deps']]
    prompt = PROMPT.format(sheet=t['sheet'], rows=json.dumps(rows,ensure_ascii=False)[:11000],
                           deps=json.dumps(deps,ensure_ascii=False)[:3000])
    msg = call(client, [{'role':'user','content':prompt}], 'claude-fable-5')
    tx=''.join(b.text for b in msg.content if b.type=='text'); m=re.search(r'\{.*\}',tx,re.S)
    res=json.loads(m.group(0))
    ch=res.get('checks',[])
    art=sum(1 for c in ch if c.get('verdict')=='artifact'); nu=sum(1 for c in ch if c.get('verdict')=='nuanced')
    print(f"ок: {t['sheet'][:34]:34} правил:{len(ch)} артефакт:{art} нюанс:{nu}", flush=True)
    return res

results=[]
with ThreadPoolExecutor(max_workers=8) as ex:
    futs={ex.submit(worker,t):t for t in tasks}
    for f in as_completed(futs):
        try: results.append(f.result())
        except Exception as e: print(f"FAIL {futs[f]['sheet'][:30]}: {repr(e)[:70]}", flush=True)
json.dump(results, open('kb/deps-verified.json','w'), ensure_ascii=False, indent=1)
allc=[c for r in results for c in r.get('checks',[])]
from collections import Counter
print('ВЕРИФИКАЦИЯ ГОТОВА. Правил:', len(allc), Counter(c.get('verdict') for c in allc))
