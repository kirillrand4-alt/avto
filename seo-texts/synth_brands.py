# -*- coding: utf-8 -*-
"""Синтез единой записи по каждому бренду из всех источников через Fable API."""
import json, re
from concurrent.futures import ThreadPoolExecutor, as_completed
from gen_provider import make_client, call

brands = json.load(open('kb/brands-assembled.json'))

PROMPT = """Ты сводишь факты о бренде компрессорного оборудования из РАЗНЫХ источников в одну
выверенную запись для базы знаний SEO-копирайтера. Источники по надёжности:
1) сайт производителя (manuf_site) - высокая; 2) прайс КЦ (price_sheets, реальные спеки) - высокая;
3) веб-поиск (websearch) - средняя-высокая; 4) брендовая страница нашего сайта (brand_page) - средняя;
5) memory-досье (dossier_excerpt) - НИЗКАЯ (написано ИИ из памяти, часто «данных мало»).

Бренд: {name}
ДАННЫЕ ПО ИСТОЧНИКАМ (JSON):
{data}

Сведи в ОДИН JSON:
- brand
- country: страна производства (с уверенностью); если источники расходятся - укажи расхождение
- founded, factories: если есть
- positioning: 1-2 фразы, чем бренд известен (только подтверждённое)
- product_types: типы выпускаемого оборудования
- series: серии с расшифровкой (объедини из прайса+сайта; расшифровку бери только подтверждённую)
- dependencies: технические закономерности (IP↔мощность, привод↔мощность, блок↔серия) - ВАЖНО, из price_sheets
- blocks_engines: винтовые блоки/двигатели
- warranty: если есть
- ready_facts: список фактов, которые МОЖНО использовать в тексте как есть
- caveats: чего НЕ утверждать (спорное/непроверенное/маркетинговые заявления)
- conflicts: расхождения между источниками (если есть)
- confidence_overall: high/medium/low

Не выдумывай. Если источник пустой - игнорируй. Если данных почти нет - confidence low и короткая запись."""

client = make_client()
def worker(kv):
    slug, b = kv
    data = json.dumps(b, ensure_ascii=False)[:9000]
    msg = call(client, [{'role':'user','content':PROMPT.format(name=b['name'], data=data)}], 'claude-fable-5')
    t = ''.join(x.text for x in msg.content if x.type=='text')
    m = re.search(r'\{.*\}', t, re.S)
    res = json.loads(m.group(0)); res['_slug']=slug
    print(f"ок: {b['name']} (conf={res.get('confidence_overall')}, conflicts={len(res.get('conflicts') or [])})", flush=True)
    return res

results=[]
with ThreadPoolExecutor(max_workers=8) as ex:
    futs={ex.submit(worker,kv):kv for kv in brands.items()}
    for f in as_completed(futs):
        try: results.append(f.result())
        except Exception as e: print(f"FAIL {futs[f][0]}: {repr(e)[:80]}", flush=True)
json.dump(results, open('kb/brands-synthesized.json','w'), ensure_ascii=False, indent=1)
conf=[x for x in results if x.get('confidence_overall')=='high']
confl=[x for x in results if x.get('conflicts')]
print(f'СИНТЕЗ ГОТОВ: {len(results)} брендов | high-conf: {len(conf)} | с расхождениями: {len(confl)}')
