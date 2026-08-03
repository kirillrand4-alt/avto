# -*- coding: utf-8 -*-
"""Генерация ОДНОЙ темы гост-поста под конкретного донора (остальные темы не трогает).

    python3 gen_single.py <slug> [--donor <домен>] [--donor-note "<контекст аудитории>"]

Отличия от gp_gen.main() (чек-лист кластера §11, пп. 1 и 4):
- выборочная генерация по slug вместо «всегда все 5»;
- gp.parse_json обёрнут try/except: битый JSON не рвёт тему, а уходит модели
  на исправление в том же диалоге (ещё одна попытка вместо потери);
- донорский контекст (аудитория площадки, региональный угол) добавляется в промпт;
- в meta пишутся donor и фактическая модель.

Модель: claude-fable-5. ВНИМАНИЕ: gen_provider.resolve_model по умолчанию считает её
мёртвой (замер 27.07.2026) и молча подменяет на opus-4-8. Проверка 03.08.2026: fable-5
ОЖИЛ. Запускать с PROVIDER_DEAD_MODELS='' чтобы получить настоящий fable-5:
    PROVIDER_DEAD_MODELS='' python3 gen_single.py podbor-vintovogo --donor samaraonline24.ru
"""
import json, os, re, sys, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gen_provider as gp
from gp_gen import THEMES, PROMPT, BYLINE, qa_article

DIR = os.path.dirname(os.path.abspath(__file__))
MODEL = 'claude-fable-5'
MAX_ATTEMPTS = 4   # 1 генерация + до 3 доводок/починок JSON

# Замер 03.08.2026 (уточняет вердикт 27.07 из resolve_model): fable-5 на шлюзе
# ПОЛУЖИВОЙ - на короткие промпты отвечает (и с thinking=False, и без), на боевые
# промпты ~11 КБ возвращает пустой text при stop_reason=end_turn (5 воспроизведений:
# с thinking - пусто, без thinking - пусто; без длинного PROVIDER_FIRST_TOKEN_SEC
# просто молчит >90с). Для генерации статей мёртв - работаем через штатную подмену
# resolve_model на claude-opus-4-8 (на нём шёл весь реген каталога).


def gen_one(theme, donor=None, donor_note=''):
    prompt = PROMPT.format(guide=open(os.path.join(DIR, 'STYLE-GUIDE-GUEST.md'),
                                      encoding='utf-8').read(), **theme)
    if donor_note:
        prompt += ('\n\n=== ПЛОЩАДКА РАЗМЕЩЕНИЯ (учесть аудиторию, факты о регионе не выдумывать) ===\n'
                   + donor_note)
    messages = [{'role': 'user', 'content': prompt}]
    t0 = time.time(); usage_out = 0
    data, issues = None, ['не сгенерировано']
    for attempt in range(MAX_ATTEMPTS):
        msg = gp.call(gp.make_client(), messages, model=MODEL, effort='xhigh')
        usage_out += msg.usage.output_tokens
        raw = ''.join(b.text for b in msg.content if b.type == 'text')
        try:
            cand = gp.parse_json(msg)
        except Exception as e:   # битый JSON: не теряем тему, просим починить в том же диалоге
            print(f'[{theme["slug"]}] попытка {attempt+1}: битый JSON ({repr(e)[:80]}), прошу исправить',
                  file=sys.stderr, flush=True)
            messages = messages + [
                {'role': 'assistant', 'content': raw},
                {'role': 'user', 'content': 'Твой ответ не распарсился как JSON. Верни СТРОГО один '
                 'валидный JSON-объект {"title": "...", "html": "..."} без пояснений и без ```-ограждений.'}]
            continue
        data = cand
        issues = qa_article(data.get('html', ''), theme['acceptor'])
        if not issues:
            break
        print(f'[{theme["slug"]}] попытка {attempt+1}: QA {len(issues)} претензий: '
              f'{"; ".join(issues)[:160]}', file=sys.stderr, flush=True)
        messages = messages + [
            {'role': 'assistant', 'content': raw},
            {'role': 'user', 'content': 'Проверка нашла нарушения:\n- ' + '\n- '.join(issues) +
             '\nИсправь ТОЛЬКО это, остальное не трогай. Верни полный JSON в том же формате.'}]
    if data is None:
        raise RuntimeError(f'JSON не получен за {MAX_ATTEMPTS} попыток')
    html = data['html'].rstrip() + '\n' + BYLINE
    open(os.path.join(DIR, f"gp-{theme['slug']}.html"), 'w', encoding='utf-8').write(
        f"<h1>{data['title']}</h1>\n" + html)
    meta = dict(slug=theme['slug'], title=data['title'], acceptor=theme['acceptor'],
                anchor_type=theme['anchor'], donor=donor, model=gp.resolve_model(MODEL),
                clean=not issues, issues=issues,
                chars=len(re.sub(r'<[^>]+>', '', html)), seconds=round(time.time() - t0),
                output_tokens=usage_out)
    json.dump(meta, open(os.path.join(DIR, f"gp-{theme['slug']}.meta.json"), 'w'),
              ensure_ascii=False, indent=1)
    return meta


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit('usage: gen_single.py <slug> [--donor <домен>] [--donor-note "<контекст>"]\n'
                 'слаги: ' + ', '.join(t['slug'] for t in THEMES))
    slug = args[0]
    donor = args[args.index('--donor') + 1] if '--donor' in args else None
    donor_note = args[args.index('--donor-note') + 1] if '--donor-note' in args else ''
    theme = next((t for t in THEMES if t['slug'] == slug), None)
    if theme is None:
        sys.exit(f'нет темы {slug}; есть: ' + ', '.join(t['slug'] for t in THEMES))
    m = gen_one(theme, donor=donor, donor_note=donor_note)
    print(json.dumps(m, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
