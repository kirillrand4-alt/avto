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
# ВАЖНО: thinking-путь шлюза в этот день отдавал пустой text на больших промптах и
# на opus-4-8 тоже, поэтому вызов - сначала thinking=False, потом gp.call как fallback
# (проверено на 4 линзах review_gp: opus-4-8 + thinking=False отработал стабильно).

NATIVE = """
=== НАТИВНАЯ МОДЕЛЬ (обязательна, приоритет над остальными правилами) ===
Статья - редакционный материал площадки, НЕ от нашей компании:
- БЕЗ байлайна и подписи автора (не добавляй ничего похожего в конец).
- НЕ упоминай названий компаний-поставщиков и продавцов; ссылку подай как отсылку
  к внешнему источнику данных (каталогу моделей), а не как рекомендацию продавца.
- Кейс перескажи обезличенно: без юрлиц, без брендов и точных артикулов - только
  класс машины и параметры (мощность, давление, ёмкость ресивера, число постов).
- Максимум ОДИН нумерованный блок на статью (чек-лист); методику и ошибки - прозой,
  без «Первый шаг/Второй шаг» и «Ошибка первая/вторая».
- «Ударный» однофразовый абзац - не больше одного за статью.
- Финал без моральной сентенции: вернись деталью к вводной сцене или оборви на
  практическом факте.
- Одно короткое содержательное отступление от темы (пара предложений, из практики).
"""


# GP_EFFORT: '' = не передавать output_config (рецепт 03.08: с effort=xhigh шлюз
# сжигает бюджет в форсированном thinking и отдаёт пустой text; без effort - работает).
EFFORT = os.environ.get('GP_EFFORT', 'xhigh') or None


def call_robust(messages):
    """Сначала thinking=False (баг шлюза 03.08), потом штатный gp.call коротким attempts."""
    last = None
    for a in range(2):
        if a:
            time.sleep(15)
        try:
            msg = gp._raw_stream(messages, MODEL, 16000, thinking=False, effort=EFFORT)
            if ''.join(b.text for b in msg.content if b.type == 'text').strip():
                return msg
            last = f'пустой ответ (thinking=False), stop={msg.stop_reason}'
        except Exception as e:
            last = f'сбой стрима: {repr(e)[:120]}'
        print(f'ретрай {a+1}/2: {last}', file=sys.stderr, flush=True)
    return gp.call(gp.make_client(), messages, model=MODEL, attempts=2, effort=EFFORT)


def gen_one(theme, donor=None, donor_note='', native=False):
    prompt = PROMPT.format(guide=open(os.path.join(DIR, 'STYLE-GUIDE-GUEST.md'),
                                      encoding='utf-8').read(), **theme)
    if donor_note:
        prompt += ('\n\n=== ПЛОЩАДКА РАЗМЕЩЕНИЯ (учесть аудиторию, факты о регионе не выдумывать) ===\n'
                   + donor_note)
    if native:
        prompt += '\n' + NATIVE
    messages = [{'role': 'user', 'content': prompt}]
    t0 = time.time(); usage_out = 0
    data, issues = None, ['не сгенерировано']
    for attempt in range(MAX_ATTEMPTS):
        msg = call_robust(messages)
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
    html = data['html'].rstrip() + ('' if native else '\n' + BYLINE)
    open(os.path.join(DIR, f"gp-{theme['slug']}.html"), 'w', encoding='utf-8').write(
        f"<h1>{data['title']}</h1>\n" + html)
    meta = dict(slug=theme['slug'], title=data['title'], acceptor=theme['acceptor'],
                anchor_type=theme['anchor'], donor=donor, model=gp.resolve_model(MODEL),
                native=native, clean=not issues, issues=issues,
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
    native = '--native' in args
    theme = next((t for t in THEMES if t['slug'] == slug), None)
    if theme is None:
        sys.exit(f'нет темы {slug}; есть: ' + ', '.join(t['slug'] for t in THEMES))
    if '--anchor' in args:   # переопределить тип якоря из THEMES (напр. брендовый для регионалки)
        theme = dict(theme, anchor=args[args.index('--anchor') + 1])
    m = gen_one(theme, donor=donor, donor_note=donor_note, native=native)
    print(json.dumps(m, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
