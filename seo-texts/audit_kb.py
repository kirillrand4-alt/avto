# -*- coding: utf-8 -*-
"""Adversarial-аудит всей сводной базы: независимый скептик метит небезопасные факты по классам."""
import json, re
from concurrent.futures import ThreadPoolExecutor, as_completed
from gen_provider import make_client, call

synth = json.load(open('kb/brands-synthesized.json'))
assembled = json.load(open('kb/brands-assembled.json'))

PROMPT = """Ты НЕЗАВИСИМЫЙ АУДИТОР качества данных. Другой ИИ свёл факты о бренде из источников
в запись для базы знаний. Твоя задача — найти НЕБЕЗОПАСНЫЕ для публикации факты. Источники по
надёжности: сайт производителя + прайс = высокая; веб-поиск = средняя-высокая; брендовая страница = средняя;
memory-досье = НИЗКАЯ (написано ИИ из памяти, часто галлюцинации для нишевых брендов).

СВЕДЁННАЯ ЗАПИСЬ:
{synth}

ИСХОДНЫЕ ИСТОЧНИКИ (что откуда):
{sources}

Найди факты, которые НЕЛЬЗЯ публиковать без проверки. Классы ошибок:
- hallucination: конкретный факт (год, цифра, технология) держится ТОЛЬКО на memory-досье, не подтверждён надёжным источником
- wrong_domain: факты о продукции не соответствуют компрессорной тематике (чужая компания)
- misattribution: факт мог прийти с листа/страницы ДРУГОГО бренда
- numeric_artifact: подозрительное число (год как давление, единицы измерения, выброс)
- overclaim: маркетинговое заявление подано как факт («крупнейший в мире», «лучший»)
- stale/contradiction: внутреннее противоречие

Верни ОДИН JSON: {{"brand":"{brand}","unsafe":[{{"fact":"...","class":"...","why":"...","action":"проверить/удалить/смягчить"}}],"overall_risk":"high/medium/low"}}
Если всё безопасно — unsafe:[] и overall_risk:low."""

client = make_client()
def worker(x):
    slug=x.get('_slug'); brand=x.get('brand',slug)
    src=assembled.get(slug,{})
    prompt=PROMPT.format(brand=brand, synth=json.dumps(x,ensure_ascii=False)[:5000],
                         sources=json.dumps(src,ensure_ascii=False)[:5000])
    msg=call(client,[{'role':'user','content':prompt}],'claude-fable-5')
    t=''.join(b.text for b in msg.content if b.type=='text'); m=re.search(r'\{.*\}',t,re.S)
    res=json.loads(m.group(0))
    u=len(res.get('unsafe',[]))
    print(f"ок: {brand[:26]:26} риск:{res.get('overall_risk'):7} небезопасных:{u}", flush=True)
    return res

results=[]
with ThreadPoolExecutor(max_workers=6) as ex:
    futs={ex.submit(worker,x):x for x in synth}
    for f in as_completed(futs):
        try: results.append(f.result())
        except Exception as e: print(f"FAIL {futs[f].get('brand')}: {repr(e)[:70]}",flush=True)
json.dump(results,open('kb/kb-audit.json','w'),ensure_ascii=False,indent=1)
allu=[(r['brand'],u) for r in results for u in r.get('unsafe',[])]
from collections import Counter
print('АУДИТ ГОТОВ. Небезопасных фактов:',len(allu),'| по классам:',Counter(u.get('class') for _,u in allu))
