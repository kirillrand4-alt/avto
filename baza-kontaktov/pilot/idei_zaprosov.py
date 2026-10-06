# -*- coding: utf-8 -*-
"""Мозговой штурм поисковых запросов через провайдерский API на нескольких моделях.
Результат: idei/<модель>.json (сырой ответ) и idei/svod.csv (слито, без дублей с zaprosy.csv).
    python3 idei_zaprosov.py [модель ...]"""
import csv, json, os, re, sys, threading
from concurrent.futures import ThreadPoolExecutor
D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(D, '..', '..', 'seo-texts'))
import gen_provider as G  # noqa: E402

# gen_provider.env() читает seo-texts/.env; ключ сессии лежит в окружении — файл с ключом не создаём
G.env = lambda: {'PROVIDER_API_KEY': os.environ['PROVIDER_API_KEY'],
                 'PROVIDER_BASE_URL': os.environ.get('PROVIDER_BASE_URL', 'https://router.cheap')}

MODELS = sys.argv[1:] or ['claude-opus-5-5', 'gpt-5.6-terra', 'deepseek-v4-pro', 'qwen3.8-max',
                          'glm-5.3', 'kimi-k3', 'gemini-3.6-flash', 'grok-4.7']
est = [r['query_template'] for r in csv.DictReader(open(os.path.join(D, '..', 'zaprosy.csv'), encoding='utf-8'))]

PROMPT = f"""Ты помогаешь собрать базу B2B-компаний РФ и Беларуси через поисковую выдачу Яндекса и Google.
Цель запроса: чтобы в топ-10 попадали СОБСТВЕННЫЕ сайты компаний-производителей/хозяйств, а не агрегаторы,
маркетплейсы, карты, СМИ, статьи, дилеры оборудования и розница.

Сегменты:
- exporters: экспортёры зерна, масличных, бобовых, масла, шрота (трейдеры, порт, FOB/CIF);
- seeds: семеноводы (элита, РС1, оригинаторы, семенные заводы, гибриды, семенной картофель);
- food: пищевые производства раздела 10 ОКВЭД (мука, крупа, масло, крахмал, комбикорм, консервы, соки, сахар и т.д.);
- elevators: элеваторы, ХПП, КХП, зернохранение, сушка и подработка зерна;
- nuts: орехи (фундук, грецкий, кедровый, переработка, сады);
- berries: ягоды (плантации, питомники ягодных, заморозка, переработка), включая Беларусь.

Итоги пилота (1-я страница выдачи):
- ЛУЧШЕ всего работали: "семена пшеницы элита РС1 от производителя", "гибриды подсолнечника производитель семян",
  "замороженная смородина оптом производитель", "питомник саженцев голубики Беларусь", "ядро кедрового ореха оптом
  производитель", "премиксы производитель", "БВМК производитель", "grain trading company Russia".
- ПЛОХО (агрегаторы, карты, статьи): "экспортёр гороха Краснодарский край", "экспорт пшеницы из России",
  "элеватор Рубцовск", "клубника плантация Липецкая область", "грецкий орех очистка цех Ставропольский край".
- Мешают: Яндекс.Карты, 2ГИС, agroserver, интернет-магазины, дилеры агрохимии и техники, производители оборудования.

Уже есть {len(est)} шаблонов, например: {'; '.join(est[::25])}.

Задание: предложи 40 НОВЫХ поисковых запросов (не перефразы уже имеющихся), которые вытащат собственные сайты
компаний в этих сегментах. Думай как закупщик или как сама компания пишет о себе на главной: профессиональный
жаргон отрасли, ГОСТ/ТУ, документы (СДИЗ, сертификат на семена, декларация), услуги, которые оказывает только
такая компания ("приёмка зерна нового урожая цена", "калибровка и протравливание семян"), названия форм
организаций (СПК, КФХ, АО "... КХП"), английские/китайские формулировки для экспортёров, типичные фразы с сайтов.
Можно плейсхолдеры {{регион}}, {{город}}, {{культура}}, {{продукт}}. Распредели по всем шести сегментам.

Ответ: ТОЛЬКО JSON-массив объектов:
[{{"segment":"seeds","query":"...","geo":"none|region|city|by","why":"кратко, почему выдаст сайты компаний"}}]"""


def _chat_stream(model, prompt):
    """OpenAI-совместимый /v1/chat/completions со стримингом (не-Anthropic модели шлюза)."""
    import httpx
    e = G.env()
    h = dict(G._RAW_HEADERS)
    h.pop('anthropic-version', None)
    h['Authorization'] = 'Bearer ' + e['PROVIDER_API_KEY']
    body = {'model': model, 'stream': True, 'max_tokens': 8000,
            'messages': [{'role': 'user', 'content': prompt}]}
    parts = []
    with httpx.stream('POST', e['PROVIDER_BASE_URL'].rstrip('/') + '/v1/chat/completions',
                      headers=h, json=body, timeout=600.0) as r:
        if r.status_code != 200:
            r.read()
            raise RuntimeError(f'HTTP {r.status_code}: {r.text[:200]}')
        for line in r.iter_lines():
            if line.startswith('data:') and line[5:].strip() not in ('', '[DONE]'):
                try:
                    d = json.loads(line[5:])
                    parts.append(((d.get('choices') or [{}])[0].get('delta') or {}).get('content') or '')
                except json.JSONDecodeError:
                    pass
    return ''.join(parts)


def one(model):
    out = os.path.join(D, 'idei', model + '.json')
    if os.path.exists(out):
        return model, json.load(open(out, encoding='utf-8')), None
    try:
        if model.startswith('claude'):
            msg = G.call(None, [{'role': 'user', 'content': PROMPT}], model=model, attempts=3)
            text = ''.join(b.text for b in msg.content if b.type == 'text')
        else:
            text = ''
            for att in range(3):
                try:
                    text = _chat_stream(model, PROMPT)
                    if '[' in text:
                        break
                except Exception as ex:  # noqa: BLE001
                    text = str(ex)
            if '[' not in text:
                raise RuntimeError(text[:200])
        m = re.search(r'\[.*\]', text, re.S)
        data = json.loads(m.group(0))
        json.dump(data, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        return model, data, None
    except Exception as e:  # noqa: BLE001
        return model, [], f'{type(e).__name__}: {str(e)[:150]}'


if __name__ == '__main__':
    norm = lambda s: re.sub(r'[^\wа-яё{} ]', '', s.lower().replace('ё', 'е')).strip()
    have = {norm(q) for q in est}
    seen, rows = {}, []
    with ThreadPoolExecutor(8) as ex:
        for model, data, err in ex.map(one, MODELS):
            print(f'{model}: {len(data)} идей' + (f' — ОШИБКА {err}' if err else ''))
            for it in data:
                q = (it.get('query') or '').strip()
                k = norm(q)
                if not q or k in have:
                    continue
                if k in seen:
                    seen[k]['models'] += '|' + model
                    continue
                seen[k] = {'segment': it.get('segment', ''), 'query': q, 'geo': it.get('geo', ''),
                           'models': model, 'why': it.get('why', '')}
    rows = sorted(seen.values(), key=lambda r: (r['segment'], -r['models'].count('|'), r['query']))
    with open(os.path.join(D, 'idei', 'svod.csv'), 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['segment', 'query', 'geo', 'models', 'why'])
        w.writeheader(); w.writerows(rows)
    print('уникальных новых:', len(rows))
