#!/usr/bin/env python3
"""Фаза 7: проверка ВСЕЙ серии разом — то, чего линзы не видят принципиально.

Каждая из 15 линз смотрит одну статью. А публикуем мы 24 текста, написанных одним
конвейером за один день, и риск здесь другого рода: не «плохая статья», а «двадцать
четыре одинаковых хороших». Три роли из четырёх в разборе (`LENS-GAPS.md`) назвали
это независимо — повторяющиеся обороты, одинаковая структура, однотипные якоря.

Случай из этой же кампании: четыре задания вышли под заголовком «Подбор винтового
компрессора для производственного цеха». Каждое по отдельности было нормальным,
линзы бы их пропустили — поймал только проход по всем джобам разом.

Работает в двух режимах:
  * по джобам (`final-jobs.jsonl`) — до генерации, ловит однообразие замысла;
  * по готовым статьям (`ready/*.final.html`) — после генерации, ловит однообразие
    исполнения: общие обороты, одинаковый ритм разделов, шаблонные концовки.

Механика считает то, что считается точно (пересечения n-грамм, распределения),
агент судит то, что требует смысла (насколько тексты выглядят одной серией).

    python3 series_check.py [--texts]
"""
from __future__ import annotations

import collections
import json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gen_provider as gp                                    # noqa: E402

OUT = os.environ.get('SERIES_OUT', 'series-check.json')
READY = 'ready'
NGRAM = 5            # длина фразы в словах: короче — шум, длиннее — почти не совпадает
MIN_DOCS = 2         # фраза интересна, если встретилась минимум в двух статьях

PROMPT = """Ты редактор, принимающий СЕРИЮ гостевых статей. Их 24, все написаны одним
конвейером за один день и уйдут на разные площадки в течение двух месяцев.

Твоя задача — не оценить каждую статью (это уже сделано), а увидеть, НЕ ВЫГЛЯДЯТ ЛИ
ОНИ ОДНОЙ СЕРИЕЙ. Читатель их вместе не увидит, но поисковая система и редактор
второй площадки — увидят. Признаки серии: общие обороты, одинаковый ритм разделов,
одинаковая логика подачи, однотипные заголовки, повторяющиеся приёмы захода и концовки.

=== ЧТО ПОСЧИТАНО МЕХАНИЧЕСКИ ===
{stats}

=== ЗАГОЛОВКИ И СТРУКТУРЫ ===
{items}

=== ЗАДАЧА ===
1. Скажи, какие статьи выглядят написанными по одному шаблону, и в чём именно шаблон.
2. Назови обороты и приёмы, которые кочуют из текста в текст.
3. Для каждой проблемной статьи скажи, что поменять — конкретно, а не «сделать
   разнообразнее».
Если серия выглядит разнородной — так и скажи, не выдумывай проблему.

=== ФОРМАТ ОТВЕТА (plain text, без markdown) ===
ВЕРДИКТ: серия однородна | серия разнородна
ОБЩИЕ ПРИЁМЫ: <что кочует между текстами; или «не найдено»>
---
СТАТЬЯ: <донор>
ПРОБЛЕМА: <в чём шаблонность>
ЧТО ПОМЕНЯТЬ: <конкретно>
---
"""


# Служебные обороты самих ЗАДАНИЙ: агент отвечает по заданному формату, и его
# формулировки («промышленная часть появляется в разделе про…») одинаковы по
# определению. В тексте статьи их не будет - генератор угол не переписывает. При
# режиме --texts фильтр не нужен, но и не мешает.
SERVICE = (
    'промышленная часть появляется', 'часть появляется в разделе',
    'как справка о типе оборудования', 'ссылка стоит', 'ссылка появляется',
    'в разделе про', 'статья про', 'угол статьи',
)


def strip_service(t):
    for ph in SERVICE:
        t = re.sub(re.escape(ph) + r'[^.;]*[.;]?', ' ', t, flags=re.I)
    return t


def norm(t):
    t = re.sub(r'<[^>]+>', ' ', t)
    t = re.sub(r'[^а-яёa-z0-9 ]+', ' ', t.lower())
    return re.sub(r'\s+', ' ', t).strip()


def ngrams(text, n=NGRAM):
    w = norm(strip_service(text)).split()
    return {' '.join(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}


def shared_phrases(docs):
    """Фразы, встречающиеся минимум в MIN_DOCS статьях. Именно они — подпись серии."""
    cnt = collections.Counter()
    for _, text in docs:
        for g in ngrams(text):
            cnt[g] += 1
    return [(g, n) for g, n in cnt.most_common() if n >= MIN_DOCS]


def load_jobs():
    return [json.loads(l) for l in open('final-jobs.jsonl', encoding='utf-8')
            if l.strip() and not json.loads(l).get('error')]


def load_texts(jobs):
    out = []
    for j in jobs:
        for name in (f"gp-{j['slug']}.final.html", f"gp-{j['slug']}.NEEDS-REVIEW.html"):
            p = os.path.join(READY, name)
            if os.path.exists(p):
                out.append((j['donor'], open(p, encoding='utf-8').read()))
                break
    return out


FIX_PROMPT = """Ты редактор серии гостевых статей. Проверка всей серии показала, что
это задание написано по тому же шаблону, что и соседние. Перепиши его так, чтобы оно
перестало быть однотипным — но осталось честным для своей площадки и целевой страницы.

=== ЗАДАНИЕ ===
площадка: {donor} ({mode})
аудитория площадки: {donor_note}
целевая страница: {url}
якорь (НЕ меняется): {anchor}
заголовок: {title}
угол: {angle}
скелет: {skeleton}

=== ЧТО НЕ ТАК ===
{problem}

=== ЧТО ПОМЕНЯТЬ ===
{fix}

=== ПРАВИЛА ===
* тема статьи и целевая страница остаются прежними — меняется подача, а не предмет;
* заголовок не должен начинаться с «Как выбрать» и «Как подобрать» — эти формулы
  уже заняты соседними статьями серии;
* структура должна отличаться от «зачем -> сравнение вариантов -> критерии подбора ->
  расчёт параметров»: это скелет половины серии;
* в скелете не должно быть служебных меток вроде «промышленная часть появляется
  в разделе» — это формулировка задания, а не название раздела;
* угол должен идти от аудитории площадки, а не от товара.

=== ФОРМАТ ОТВЕТА (plain text, без markdown) ===
ЗАГОЛОВОК: <новый заголовок>
УГОЛ: <3-5 предложений>
СКЕЛЕТ: <структура, разделы через ->>
"""


def _apply(jobs, problems):
    """Переписать задания, которые проверка серии назвала шаблонными."""
    import concurrent.futures as cf
    by = {j['donor']: j for j in jobs}
    # Агент называет статью с пояснением: «truckmix.ru (дизельный передвижной
    # компрессор)». Домен - первое слово, остальное отбрасываем.
    todo = []
    for p in problems:
        j = by.get(p['donor']) or by.get(p['donor'].split()[0].strip('«»"'))
        if j:
            todo.append((p, j))

    def one(item):
        p, j = item
        prompt = FIX_PROMPT.format(
            donor=j['donor'], mode=j.get('mode', ''), donor_note=(j.get('donor_note') or '')[:220],
            url=j['url'], anchor=j['anchor'], title=j.get('title', ''),
            angle=(j.get('angle') or '')[:420], skeleton=(j.get('skeleton') or '')[:300],
            problem=p['problem'], fix=p['fix'])
        try:
            msg = gp.call(None, [{'role': 'user', 'content': prompt}],
                          model='claude-fable-5', attempts=4)
            raw = ''.join(b.text for b in msg.content if b.type == 'text').strip().replace('*', '')
        except Exception as e:                               # noqa: BLE001
            return j['donor'], None, repr(e)[:110]
        gg = lambda k: (re.search(rf'^{k}:\s*(.+?)(?=\n[А-ЯA-Z][А-ЯA-Z ]{{2,}}:|\Z)',
                                  raw, re.S | re.M) or [None, ''])[1].strip()
        return j['donor'], {'title': gg('ЗАГОЛОВОК'), 'angle': gg('УГОЛ'),
                            'skeleton': gg('СКЕЛЕТ')}, None

    print('\nпереписываю шаблонные задания:', len(todo), flush=True)
    n = 0
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        for dom, upd, err in ex.map(one, todo):
            if not upd or not upd.get('title'):
                print('  %-28s ОШИБКА %s' % (dom, err or 'пустой ответ'), flush=True)
                continue
            j = by[dom]
            j['title_series_old'], j['title'] = j.get('title'), upd['title']
            j['angle_series_old'], j['angle'] = j.get('angle'), upd['angle']
            if upd.get('skeleton'):
                j['skeleton_series_old'], j['skeleton'] = j.get('skeleton'), upd['skeleton']
            n += 1
            print('  %-28s %s' % (dom, upd['title'][:62]), flush=True)
    with open('final-jobs.jsonl', 'w', encoding='utf-8') as f:
        for j in jobs:
            f.write(json.dumps(j, ensure_ascii=False) + '\n')
    print('переписано:', n)


def main():
    use_texts = '--texts' in sys.argv
    jobs = load_jobs()
    if use_texts:
        docs = load_texts(jobs)
        if not docs:
            print('готовых статей в ready/ нет — запусти без --texts, по джобам')
            return 1
        source = 'готовые статьи'
    else:
        docs = [(j['donor'], ' '.join(str(j.get(k) or '') for k in
                                      ('title', 'angle', 'skeleton', 'case'))) for j in jobs]
        source = 'джобы (замысел, до генерации)'

    shared = shared_phrases(docs)
    heads = collections.Counter()
    for j in jobs:
        t = norm(j.get('title') or '')
        heads[' '.join(t.split()[:2])] += 1
    sk_len = [len(re.split(r'->|→|>>', j.get('skeleton') or '')) for j in jobs]
    anchors = collections.Counter(j['anchor'].lower() for j in jobs)
    pages = collections.Counter(j['url'] for j in jobs)
    stats = [
        f'источник: {source}, документов {len(docs)}',
        f'фраз по {NGRAM} слов, встречающихся в 2+ статьях: {len(shared)}',
    ]
    if shared:
        stats.append('  самые частые: ' + '; '.join(f'«{g}» ×{n}' for g, n in shared[:8]))
    rep_heads = [(h, n) for h, n in heads.most_common() if n > 1]
    stats.append('одинаковые начала заголовков: ' +
                 ('; '.join(f'«{h}…» ×{n}' for h, n in rep_heads) if rep_heads else 'нет'))
    stats.append(f'разделов в скелете: от {min(sk_len)} до {max(sk_len)}, '
                 f'медиана {sorted(sk_len)[len(sk_len) // 2]}')
    dup_a = [(a, n) for a, n in anchors.most_common() if n > 1]
    stats.append('повторяющиеся якоря: ' +
                 ('; '.join(f'«{a}» ×{n}' for a, n in dup_a) if dup_a else 'нет'))
    dup_p = [(p, n) for p, n in pages.most_common() if n > 2]
    stats.append('страницы с 3+ ссылками: ' +
                 ('; '.join(f'{p} ×{n}' for p, n in dup_p) if dup_p else 'нет (лимит 2 держится)'))

    items = '\n'.join(
        f"* {j['donor']} ({j.get('mode')}): {j.get('title', '')}\n"
        f"    скелет: {(j.get('skeleton') or '')[:190]}" for j in jobs)
    print('\n'.join(stats), '\n', flush=True)

    msg = gp.call(None, [{'role': 'user', 'content': PROMPT.format(
        stats='\n'.join(stats), items=items)}], model='claude-fable-5', attempts=4)
    raw = ''.join(b.text for b in msg.content if b.type == 'text').strip().replace('*', '')
    g = lambda k, blk: (re.search(rf'^{k}:\s*(.+?)(?=\n[А-ЯA-Z][А-ЯA-Z ]{{2,}}:|\Z)',
                                  blk, re.S | re.M) or [None, ''])[1].strip()
    problems = []
    for blk in raw.split('---'):
        if g('СТАТЬЯ', blk):
            problems.append({'donor': g('СТАТЬЯ', blk), 'problem': g('ПРОБЛЕМА', blk),
                             'fix': g('ЧТО ПОМЕНЯТЬ', blk)})
    res = {'source': source, 'verdict': g('ВЕРДИКТ', raw), 'common': g('ОБЩИЕ ПРИЁМЫ', raw),
           'shared_phrases': shared[:40], 'problems': problems, 'raw': raw}
    json.dump(res, open(OUT, 'w'), ensure_ascii=False, indent=1)
    if '--fix' in sys.argv and problems:
        _apply(jobs, problems)
    print('ВЕРДИКТ:', res['verdict'])
    print('ОБЩИЕ ПРИЁМЫ:', (res['common'] or '')[:400])
    print('\nстатей с замечаниями:', len(problems))
    for p in problems:
        print('  %-28s %s' % (p['donor'], p['problem'][:80]))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
