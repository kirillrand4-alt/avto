# -*- coding: utf-8 -*-
"""Мозговой штурм источников новостей-лидов через несколько моделей (провайдер).
Каждая модель предлагает ОТКУДА ещё брать капекс-сигналы (РФ) и КАК технически тянуть.
Запуск: python3 news_ideas.py  (PROVIDER_API_KEY). Резюмируемо не нужно — быстрый прогон.
"""
import os, sys, json, re, time, pathlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_provider as G

SCR = pathlib.Path('/tmp/claude-0/-home-user-avto/bcce55cd-293a-515c-9700-ae71a77daa5a/scratchpad')
MODELS = ['claude-fable-5', 'claude-opus-4-8', 'claude-sonnet-5']

PROMPT = """Ты — эксперт по B2B lead-generation в РФ и по OSINT-сбору сигналов о капитальных вложениях.
Контекст: мы (ООО «Руспром») продаём (а) компрессоры + генераторы азота/кислорода + компрессорные
станции — нужны почти любому производству; (б) фотосепараторы и рентген-инспекцию (Meyer) — зерно/
пищёвка/вторсырьё/руда/логистика. Ищем компании, которые СТРОЯТ/расширяют/модернизируют производство,
запускают цех/линию, получили займ ФРП, стали резидентами ОЭЗ/ТОР/индустриального парка — им скоро
понадобится наше оборудование. Уже используем: Google News RSS, zakupki.gov.ru, hh.ru, ФРП, VK, региональные RSS.

Задача: предложи МАКСИМАЛЬНО полный список ДОПОЛНИТЕЛЬНЫХ источников капекс-сигналов в РФ, которые мы
ещё НЕ используем, и для КАЖДОГО — конкретный способ технического сбора. Приоритет — малые города/районы
(там меньше конкуренции за лид). Верни СТРОГО JSON без markdown:
{"sources":[{"name":"<источник>","what_signal":"<какой сигнал ловим>","division":"kc|meyer|both",
"how":"<как технически тянуть: RSS/официальный API/парсинг HTML/через прокси/браузер; конкретный URL или эндпоинт если знаешь>",
"coverage":"<федерально|региональн|малые города|отраслевой>","effort":"low|medium|high","reliability":"high|medium|low"}],
"methods":["<общие приёмы улучшить сбор: посрегионный свип, гиперлокал, дедуп, обогащение и т.п.>"]}
Будь конкретным и практичным (реальные РФ-порталы/реестры/СМИ/API). Не выдумывай несуществующее."""


def run(model):
    for _ in range(3):
        try:
            msg = G._raw_stream([{'role': 'user', 'content': PROMPT}], model, 6000, thinking=False)
            txt = ''.join(b.text for b in msg.content if b.type == 'text')
            m = re.search(r'\{.*\}', txt, re.S)
            if m:
                return json.loads(m.group(0))
        except Exception as e:
            time.sleep(3)
    return {'error': 'no-output'}


def main():
    out = {}
    for model in MODELS:
        print(f'{model} ...', flush=True)
        out[model] = run(model)
        n = len(out[model].get('sources', [])) if isinstance(out[model], dict) else 0
        print(f'  -> {n} источников', flush=True)
    (SCR / 'news_ideas_raw.json').write_text(json.dumps(out, ensure_ascii=False, indent=1))
    # дедуп-свод по name (нормализованному)
    seen, merged = {}, []
    for model, d in out.items():
        for s in (d.get('sources') or []):
            key = re.sub(r'\s+', '', (s.get('name') or '').lower())[:40]
            if not key:
                continue
            if key in seen:
                seen[key]['by'].append(model)
            else:
                seen[key] = {**s, 'by': [model]}
                merged.append(seen[key])
    # приоритет: сколько моделей согласны + reliability + малые города
    def score(s):
        return (len(s.get('by', [])), s.get('reliability') == 'high',
                'мал' in (s.get('coverage') or '') or 'район' in (s.get('coverage') or ''))
    merged.sort(key=score, reverse=True)
    (SCR / 'news_ideas_merged.json').write_text(json.dumps(merged, ensure_ascii=False, indent=1))
    print(f'\nИТОГ: {len(merged)} уникальных источников (из {len(MODELS)} моделей)', flush=True)
    for s in merged[:25]:
        print(f"  [{len(s['by'])}✓ {s.get('effort','?')}/{s.get('reliability','?')}] {s.get('name','')[:40]} "
              f"({s.get('division','')},{s.get('coverage','')[:12]}) — {s.get('how','')[:70]}", flush=True)


if __name__ == '__main__':
    main()
