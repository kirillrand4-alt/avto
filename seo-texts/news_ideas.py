# -*- coding: utf-8 -*-
"""Мозговой штурм источников новостей-лидов — РАЗНЫЕ ЛИНЗЫ одной модели (fable).
Каждая линза = свой экспертный ракурс fable, вскрывает разные типы источников
капекс-сигналов (РФ). Затем дедуп+ранжирование. Запуск: python3 news_ideas.py
"""
import os, sys, json, re, time, pathlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_provider as G

SCR = pathlib.Path('/tmp/claude-0/-home-user-avto/bcce55cd-293a-515c-9700-ae71a77daa5a/scratchpad')
MODEL = 'claude-fable-5'

# РАЗНЫЕ ЛИНЗЫ fable — каждая вскрывает свой пласт источников
LENSES = {
    'osint-реестры': 'Ты OSINT-аналитик по открытым данным РФ. Думай про ГОСУДАРСТВЕННЫЕ РЕЕСТРЫ и открытые '
        'данные: ГИСП, СПИК, реестры резидентов ОЭЗ/ТОР/индустриальных парков, ЕГРЮЛ-изменения (новые ОКВЭД/'
        'филиалы/увеличение УК), РАФП/ФРП, порталы раскрытия, Росстат/ЕМИСС, разрешения на строительство (ИСОГД).',
    'региональный-журналист': 'Ты редактор регионального делового СМИ. Думай про ГИПЕРЛОКАЛ и МАЛЫЕ ГОРОДА: '
        'сайты правительств/минпромов регионов, районные газеты, региональные инвестпорталы, пресс-службы '
        'администраций, телеграм-каналы районов, «Ъ-регион», региональные РБК/Интерфакс.',
    'отраслевик': 'Ты эксперт отраслевых ассоциаций и B2B-медиа. Думай про ОТРАСЛЕВЫЕ источники под наши '
        'направления: пищёвка/зерно/АПК (agroinvestor, zol.ru, «Агроэксперт»), металлургия/руда (metalinfo, '
        'rudmet), вторсырьё/РОП (реформа ТКО, РЭО), машиностроение (i-mash), выставки/анонсы вводов мощностей.',
    'тендеры-госзаказ': 'Ты специалист по закупкам. Думай про ТЕНДЕРНЫЕ и B2B-площадки как ранний сигнал: '
        'zakupki.gov (44/223-ФЗ) по ОКПД2 оборудования И по стройке цехов, коммерческие ЭТП (B2B-Center, '
        'Fabrikant, ТЭК-Торг, Росэлторг-коммерция), планы закупок, конкурсы на проектирование заводов.',
    'инвест-развитие': 'Ты аналитик инвестпроектов. Думай про АНОНСЫ КАПВЛОЖЕНИЙ: инвестпорталы регионов, '
        'соглашения на ПМЭФ/ИННОПРОМ/региональных форумах, корпоративные пресс-релизы о строительстве заводов, '
        'банки развития (ВЭБ, Корпорация МСП), особые преференции, «фабрики проектного финансирования».',
}

BASE = ("""Контекст: ООО «Руспром» продаёт (а) компрессоры + генераторы азота/кислорода + компрессорные станции
(нужны почти любому производству); (б) фотосепараторы и рентген-инспекцию Meyer (зерно/пищёвка/вторсырьё/руда/
логистика). Ищем компании, которые СТРОЯТ/расширяют/модернизируют производство, запускают цех/линию, получили
займ ФРП, стали резидентами ОЭЗ/ТОР/индустриального парка — им скоро понадобится наше оборудование.
Уже используем: Google News RSS, zakupki.gov.ru, hh.ru, ФРП, VK, региональные RSS.

Через СВОЮ ЛИНЗУ предложи максимально полный список ДОПОЛНИТЕЛЬНЫХ источников капекс-сигналов в РФ, которые мы
ещё НЕ используем, и для КАЖДОГО — конкретный способ технического сбора. Приоритет — малые города/районы.
Верни СТРОГО JSON без markdown:
{"sources":[{"name":"<источник>","what_signal":"<сигнал>","division":"kc|meyer|both",
"how":"<как тянуть: RSS/официальный API/парсинг HTML/через прокси/браузер; URL или эндпоинт если знаешь>",
"coverage":"<федерально|региональн|малые города|отраслевой>","effort":"low|medium|high","reliability":"high|medium|low"}]}
Будь конкретным (реальные РФ-порталы/реестры/СМИ/API). Не выдумывай несуществующее.""")


def run_lens(lens_desc):
    prompt = lens_desc + '\n\n' + BASE
    for _ in range(4):
        try:
            msg = G._raw_stream([{'role': 'user', 'content': prompt}], MODEL, 6000, thinking=False)
            txt = ''.join(b.text for b in msg.content if b.type == 'text')
            m = re.search(r'\{.*\}', txt, re.S)
            if m:
                return json.loads(m.group(0))
        except Exception:
            time.sleep(4)
    return {'error': 'no-output'}


def main():
    out = {}
    for name, desc in LENSES.items():
        print(f'линза «{name}» ...', flush=True)
        out[name] = run_lens(desc)
        n = len(out[name].get('sources', [])) if isinstance(out[name], dict) else 0
        print(f'  -> {n} источников', flush=True)
    (SCR / 'news_ideas_raw.json').write_text(json.dumps(out, ensure_ascii=False, indent=1))
    seen, merged = {}, []
    for lens, d in out.items():
        for s in (d.get('sources') or []):
            key = re.sub(r'\s+', '', (s.get('name') or '').lower())[:40]
            if not key:
                continue
            if key in seen:
                seen[key]['by'].append(lens)
            else:
                seen[key] = {**s, 'by': [lens]}
                merged.append(seen[key])

    def score(s):
        return (len(s.get('by', [])), s.get('reliability') == 'high', s.get('effort') == 'low',
                'мал' in (s.get('coverage') or '') or 'район' in (s.get('coverage') or ''))
    merged.sort(key=score, reverse=True)
    (SCR / 'news_ideas_merged.json').write_text(json.dumps(merged, ensure_ascii=False, indent=1))
    print(f'\nИТОГ: {len(merged)} уникальных источников (из {len(LENSES)} линз fable)', flush=True)
    for s in merged[:30]:
        print(f"  [{len(s['by'])}✓ {s.get('effort','?')}/{s.get('reliability','?')}] {s.get('name','')[:38]} "
              f"({s.get('division','')},{(s.get('coverage') or '')[:11]}) — {(s.get('how') or '')[:66]}", flush=True)


if __name__ == '__main__':
    main()
