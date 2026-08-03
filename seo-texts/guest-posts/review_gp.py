# -*- coding: utf-8 -*-
"""Ревью НАШЕГО гост-поста (gp-<slug>.html) четырьмя линзами через провайдера:
филолог, инженер, линкбилдер+редактор донора (с контекстом площадки), анти-ИИ.

    PROVIDER_FIRST_TOKEN_SEC=300 python3 review_gp.py <slug> [--donor <домен>]

Выход: review-gp-<slug>.md. Паттерн - review_sample.py, отличия:
- статья по слагу из gp-<slug>.html, а не захардкоженный образец;
- линза линкбилдера знает реального донора (аудитория, регион);
- обход бага шлюза 03.08: thinking-путь на больших промптах отдаёт пустой text,
  поэтому сначала пробуем thinking=False, потом gp.call как fallback."""
import os, re, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gen_provider as gp
from review_philolog import PERSONA as PHILOLOG
from review_engineer import PERSONA as ENGINEER
from review_sample import ANTIAI

DIR = os.path.dirname(os.path.abspath(__file__))
MODEL = 'claude-fable-5'   # resolve_model сам подменит на живую (03.08 это opus-4-8)

DONOR_NOTES = {
    'samaraonline24.ru': 'региональный новостной портал Самарской области; аудитория - '
                         'руководители, снабженцы и инженеры местных предприятий',
}

LINKBUILDER_GP = """Ты - опытный SEO-специалист по линкбилдингу и одновременно выпускающий редактор
площадки {donor} ({donor_note}), принимаешь гост-посты. Оцени статью, подготовленную для размещения
на этой площадке со ссылкой на {acceptor}, по двум осям:
А) Как РЕДАКТОР ДОНОРА: взял бы такой материал? польза читателю площадки, самодостаточность,
не выглядит ли рекламой, уместен ли региональный угол, качество для площадки.
Б) Как ЛИНКБИЛДЕР АКЦЕПТОРА: якорь и его тип, положение ссылки, релевантность донор-акцептор,
риски (Минусинск/link spam/переоптимизация якоря), что улучшить в ссылочной механике.
Дай конкретные находки и в конце: 2 оценки по 10-балльной (донор/акцептор) + 3 главных улучшения."""


def call_robust(prompt):
    """Сначала thinking=False (баг шлюза 03.08: thinking на больших промптах -> пустой text),
    потом штатный gp.call с коротким attempts как fallback."""
    messages = [{'role': 'user', 'content': prompt}]
    last = None
    for a in range(2):
        if a:
            time.sleep(15)
        try:
            msg = gp._raw_stream(messages, MODEL, 8000, thinking=False, effort='high')
            text = ''.join(b.text for b in msg.content if b.type == 'text')
            if text.strip():
                return msg
            last = f'пустой ответ (thinking=False), stop={msg.stop_reason}'
        except Exception as e:
            last = f'сбой стрима: {repr(e)[:120]}'
        print(f'  ретрай {a+1}/2: {last}', file=sys.stderr, flush=True)
    return gp.call(gp.make_client(), messages, model=MODEL, attempts=2)


def one(name, persona, article):
    t0 = time.time()
    try:
        msg = call_robust(persona + '\n\n=== СТАТЬЯ (гост-пост, готовится к размещению) ===\n' + article)
        out = ''.join(b.text for b in msg.content if b.type == 'text').strip()
        return name, out, round(time.time() - t0), msg.usage.output_tokens
    except Exception as e:
        return name, f'[сбой: {e!r}]', round(time.time() - t0), 0


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit('usage: review_gp.py <slug> [--donor <домен>]')
    slug = args[0]
    donor = args[args.index('--donor') + 1] if '--donor' in args else None
    article = open(os.path.join(DIR, f'gp-{slug}.html'), encoding='utf-8').read()
    acceptor = (re.search(r'href="([^"]+)"', article) or [None, '?'])[1]
    lb = LINKBUILDER_GP.format(donor=donor or 'отраслевой портал',
                               donor_note=DONOR_NOTES.get(donor, 'сторонняя площадка под гост-посты'),
                               acceptor=acceptor)
    personas = [('Филолог', PHILOLOG), ('Инженер', ENGINEER),
                ('Линкбилдер+редактор донора', lb), ('Анти-ИИ детектор', ANTIAI)]
    res = {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(one, n, p, article): n for n, p in personas}
        for f in as_completed(futs):
            n, out, sec, tok = f.result()
            res[n] = out
            print(f'готово: {n} ({sec}с, {tok} ток.)', flush=True)
    parts = [f'# Ревью гост-поста gp-{slug}.html ({gp.resolve_model(MODEL)}, донор: {donor or "-"})\n']
    for n, _ in personas:
        parts.append(f'\n\n# {n}\n\n{res[n]}')
    out_path = os.path.join(DIR, f'review-gp-{slug}.md')
    open(out_path, 'w', encoding='utf-8').write('\n'.join(parts))
    print('=>', out_path)


if __name__ == '__main__':
    main()
