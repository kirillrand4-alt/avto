# -*- coding: utf-8 -*-
"""Инженерный sweep по списку страниц пачками по 10, с парсимым выводом (слаг -> критичность).
Устойчив к обрыву: каждая пачка пишется в eng-sweep/<n>.txt, при повторном запуске готовые пропускаются.
Выход: engineer-flagged.txt (слаги с critical/important) + eng-sweep-report.md."""
import json, os, re, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
import gen_provider as gp

DIR = os.path.dirname(os.path.abspath(__file__))
# кэш/выводы по имени входного файла, чтобы параллельные прогоны (фасеты/бренды) не сталкивались
_TAG = re.sub(r'\W+', '_', os.path.basename(sys.argv[1])).replace('_txt', '') if len(sys.argv) > 1 else 'sweep'
CACHE = os.path.join(DIR, f'eng-sweep-{_TAG}')
os.makedirs(CACHE, exist_ok=True)

HEAD = """Ты - главный инженер по компрессорному оборудованию и пневмосистемам (20 лет практики).
Проверь ТЕХНИЧЕСКУЮ ТОЧНОСТЬ связующей прозы и выводов (фактуру из прайса не трогай - она верна).

Ищи инженерные ошибки: неверные зависимости (давление/производительность обратны при одной мощности!),
переставленная/усечённая цепочка подготовки воздуха (канон: компрессор->концевой охладитель->циклон->
ресивер->префильтр->осушитель->магистральный фильтр), адсорбция как «химический» процесс (она физическая),
занижённый ресивер (норма 10-20% минутной производительности), путаница объёмный/массовый расход, л/с vs
м³/мин, «осушитель до -40» без уточнения что адсорбционный, опасные/некорректные советы.

Тебе дают 10 текстов, у каждого есть ID (===ID: <slug>===).
Верни РОВНО по одной строке на текст, СТРОГО в формате:
<slug> | <critical|important|minor|clean> | <очень краткое описание ошибки или ->
Никакого другого текста, только 10 строк. critical=грубая физ/тех ошибка, important=заметная неточность,
minor=косметика, clean=ошибок нет."""


def readable(slug):
    d = json.load(open(os.path.join(DIR, f'gen/result-{slug}.json')))
    p = json.load(open(os.path.join(DIR, f'gen/payload-{slug}.json')))
    txt = re.sub(r'<[^>]+>', ' ', d['text_html'])
    txt = re.sub(r'\s+', ' ', txt.replace('&nbsp;', ' ')).strip()
    return f'===ID: {slug}===\n[{p["category"]}] {p["h1"]}\n{txt}\n'


def do_batch(idx, slugs, client):
    cf = os.path.join(CACHE, f'{idx}.txt')
    if os.path.exists(cf):
        return idx, open(cf, encoding='utf-8').read()
    corpus = '\n\n'.join(readable(s) for s in slugs)
    prompt = HEAD + '\n\n=== 10 ТЕКСТОВ ===\n' + corpus
    try:
        msg = gp.call(client, [{'role': 'user', 'content': prompt}], model='claude-fable-5')
        out = ''.join(b.text for b in msg.content if b.type == 'text').strip()
    except Exception as e:
        out = f'[batch {idx} FAIL: {e!r}]'
    open(cf, 'w', encoding='utf-8').write(out)
    return idx, out


def main():
    slugs = [l.strip() for l in open(os.path.join(DIR, sys.argv[1])) if l.strip()]
    batches = [slugs[i:i + 10] for i in range(0, len(slugs), 10)]
    client = gp.make_client()
    results = {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(do_batch, i, b, client): i for i, b in enumerate(batches, 1)}
        for f in as_completed(futs):
            i, out = f.result(); results[i] = out
            print(f'пачка {i}/{len(batches)}', flush=True)
    # разбор: слаг -> severity
    flagged = []; rows = []
    for i in sorted(results):
        for line in results[i].splitlines():
            m = re.match(r'\s*([a-z0-9_.-]+)\s*\|\s*(critical|important|minor|clean)\s*\|\s*(.*)', line, re.I)
            if m:
                slug, sev, err = m.group(1), m.group(2).lower(), m.group(3).strip()
                rows.append((slug, sev, err))
                if sev in ('critical', 'important'):
                    flagged.append(slug)
    open(os.path.join(DIR, f'engineer-flagged-{_TAG}.txt'), 'w').write('\n'.join(dict.fromkeys(flagged)) + '\n')
    from collections import Counter
    sc = Counter(r[1] for r in rows)
    rep = [f'# Инженерный sweep: {_TAG}\n', f'Разобрано строк: {len(rows)} | {dict(sc)}\n',
           f'Флагнуто (critical+important) на регенерацию: {len(set(flagged))}\n', '## Critical\n']
    for s, sev, e in rows:
        if sev == 'critical':
            rep.append(f'- `{s}` — {e}')
    rep.append('\n## Important\n')
    for s, sev, e in rows:
        if sev == 'important':
            rep.append(f'- `{s}` — {e}')
    open(os.path.join(DIR, f'eng-sweep-report-{_TAG}.md'), 'w', encoding='utf-8').write('\n'.join(rep))
    print(f'ИТОГ: строк {len(rows)} {dict(sc)} | флагнуто {len(set(flagged))}')


if __name__ == '__main__':
    main()
