#!/usr/bin/env python3
"""Фаза 6: якоря из живых запросов — по агенту на пару.

Первая версия спрашивала ОДИН агент про все 24 пары сразу: промпт на 39 тысяч
символов, внимание размазано на двадцать четыре решения, на страницу приходилось
по 18 запросов из двух тысяч. Владелец: «может отдать агентам чтобы они сами
выбрали». Верно — теперь на каждую пару свой агент, он видит больше запросов и
думает про одну статью. Повторы якорей между площадками ловит отдельный проход
в конце (`_dedupe`), потому что агенты друг о друге не знают.

Исходная постановка задачи ниже.

Итоговые якоря выбирал `dispatch_pages.py`, а он видел только четыре слота из плана
v15 — они собраны из адреса страницы («тип товара + определение + бренд + параметр»),
а не из того, что люди на самом деле ищут.

Поправка владельца: смотреть надо не только запросы, по которым страница уже в топе.
Ссылка ценнее там, где запрос близок, но не дотягивает — поднять фразу с 15-й позиции
на 8-ю даёт больше, чем улучшить ту, что и так на 4,3. Поэтому агент получает три
среза из полного списка запросов страницы (у винтовых prokompressor их 2047, а не
12 из отобранного листа):

* топ по показам — чем страница живёт;
* полоса позиций 8-30 при показах от 20 — то, что ссылка реально может дотянуть;
* полоса позиций 5-30 в ЯНДЕКСЕ — для страниц, которые качаются под него
  (`ac-kompressor.ru/catalog/xas/`: 457 показов на 9,1 в Яндексе против 59 на 13,9
  в Google).

Страницы не трогаем: они назначены отдельным решением.

    python3 anchor_fix.py
"""
from __future__ import annotations

import json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gen_provider as gp                                    # noqa: E402
from plan_jobs import decisions, load                        # noqa: E402

OUT = os.environ.get('ANCHOR_OUT', 'anchors.json')

PROMPT = """=== РЕШЕНИЯ ВЛАДЕЛЬЦА (приоритет выше любых расчётов) ===
{decisions}

=== ЗАДАЧА ===
Подбери текст якоря для ОДНОЙ ссылки. Страница уже назначена и НЕ меняется.

Ниже: площадка, тип статьи, её заголовок, целевая страница и запросы этой страницы
тремя срезами.

Как выбирать:
1. **Тематические статьи** — якорь из живых запросов, предпочтительно из полосы
   «дотягиваемые» (позиции 8-30): именно их ссылка поднимает. Якорь должен читаться
   как фраза в тексте, а не как строка из поиска: «винтовые компрессоры для
   производства» вместо «винтовой компрессор купить цена». Падеж согласуй с фразой.
2. **Жанровые статьи** (площадка не про промышленность) — решай по КОНТЕКСТУ своей
   статьи, а не по запрету. Все эти площадки по условиям карточки принимают
   нетематические ссылки, а владелец отдельно решил, что анкорной переоптимизации
   мы не опасаемся. Поэтому:
   * если в тексте статьи есть место, куда нормальный товарный якорь встаёт
     естественно («промышленные компрессоры высокого давления» в статье про
     баротравму, «компрессор для покрасочной камеры» в статье о производстве
     мебели) — бери его, он полезнее брендового;
   * если статья совсем не про технику и любой товарный якорь будет торчать
     (подборка цитат, светская хроника) — тогда брендовый («Компрессор Центр»,
     «BERG», «ENGER») или безанкорный (домен).
   Брендовый якорь не работает ни на один коммерческий запрос, поэтому ставить
   его по умолчанию — потеря размещения.
3. Для страниц под Яндекс бери запрос из яндексового среза.
4. Якорь — 2-5 слов. Не предложение.
5. Якорь должен быть согласован с фразой, в которую встанет: проверь падеж.

=== ПАРА ===
{pairs}

=== ФОРМАТ ОТВЕТА (строго, plain text, ровно две строки, без markdown) ===
ЯКОРЬ: <текст якоря>
ПОЧЕМУ: <из какого среза взят и почему именно он>
"""


def srez(page, key, title, limit):
    lst = (page.get(key) or [])[:limit]
    if not lst:
        return ''
    out = [f'    {title}:']
    for a in lst:
        yp = f", Яндекс {a['pos_yandex']}" if a.get('pos_yandex') else ''
        out.append(f"      {a['q']} — {a['imp90']} показов, Google {a['pos']}{yp}")
    return '\n'.join(out)


def block_for(j, pages, v15):
    site, path = j['url'].replace('https://', '').split('/', 1)
    p = pages.get((site, '/' + path.rstrip('/')), {})
    b = [f"площадка: {j['donor']} ({j['mode']})",
         f"статья: {j.get('title', '')}",
         f"угол: {(j.get('angle') or '')[:260]}",
         f"целевая страница: {j['url']}",
         f"текущий якорь (можно заменить): {j['anchor']}"]
    taken = os.environ.get('ANCHORS_TAKEN', '')
    if taken:
        # Агенты работают параллельно и не знают о выборе соседей. При переигровке
        # конфликта передаём занятые якоря явно, иначе повтор воспроизведётся.
        b.append('ЯКОРЯ, УЖЕ ЗАНЯТЫЕ ДРУГИМИ СТАТЬЯМИ (повторять нельзя): ' + taken)
    if p:
        b.append(f"запросов у страницы всего: {p.get('queries_total', '?')}")
        # Срезы шире, чем в версии «один агент на всё»: агент теперь думает про
        # одну пару, и ему есть куда смотреть.
        for key, title, lim in (('anchors_reach', 'ДОТЯГИВАЕМЫЕ (позиции 8-30)', 15),
                                ('anchors_top', 'топ по показам', 10),
                                ('anchors_yandex', 'яндексовый срез (позиции 5-30)', 8)):
            s_ = srez(p, key, title, lim)
            if s_:
                b.append(s_)
    else:
        row = next((r for r in v15 if r['site'] == site
                    and r['page'].rstrip('/') == '/' + path.rstrip('/')), None)
        anc = [a for a in ((row or {}).get('anchors') or {}).values() if a]
        b.append('живых запросов нет (новая страница), слоты плана: ' + ' | '.join(anc))
    return '\n'.join(b)


def one(args):
    j, prompt = args
    try:
        msg = gp.call(None, [{'role': 'user', 'content': prompt}],
                      model='claude-fable-5', attempts=4)
        raw = ''.join(b.text for b in msg.content if b.type == 'text').strip().replace('*', '')
    except Exception as e:                                   # noqa: BLE001
        return {'donor': j['donor'], 'error': repr(e)[:130]}
    g = lambda k: (re.search(rf'^{k}:\s*(.+)$', raw, re.M) or [None, ''])[1].strip()
    return {'donor': j['donor'], 'anchor': g('ЯКОРЬ'), 'why': g('ПОЧЕМУ')}


def _dedupe(res, jobs):
    """Агенты друг о друге не знают — одинаковые якоря на разных площадках возможны.

    Брендовые и безанкорные повторы допустимы и даже нормальны (это профиль бренда),
    а вот два одинаковых коммерческих якоря на разные площадки — уже след шаблона.
    """
    import collections
    mode = {j['donor']: j['mode'] for j in jobs}
    seen = collections.defaultdict(list)
    for d, r in res.items():
        if r.get('anchor'):
            seen[r['anchor'].lower()].append(d)
    dup = {a: ds for a, ds in seen.items() if len(ds) > 1
           and any(mode.get(d) == 'тематический' for d in ds)}
    return dup


def main():
    cards, v15, pq, sem, th = load()
    pages = {(r['site'], r['page'].rstrip('/')): r
             for r in json.load(open('plan-queries.json', encoding='utf-8'))}
    jobs = [json.loads(l) for l in open('final-jobs.jsonl', encoding='utf-8') if l.strip()]
    jobs = [j for j in jobs if not j.get('error')]
    want = set(sys.argv[1:])
    todo = [j for j in jobs if not want or j['donor'] in want]
    print('пар:', len(todo), '| по агенту на пару', flush=True)
    tasks = [(j, PROMPT.format(decisions=decisions(), pairs=block_for(j, pages, v15)))
             for j in todo]
    res = {}
    import concurrent.futures as cf
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        for r in ex.map(one, tasks):
            if r.get('anchor'):
                res[r['donor']] = r
            print('  %-28s %-36s %s' % (r['donor'], (r.get('anchor') or 'ОШИБКА')[:36],
                                        (r.get('why') or r.get('error') or '')[:52]), flush=True)
    json.dump(res, open(OUT, 'w'), ensure_ascii=False, indent=1)
    dup = _dedupe(res, jobs)
    if dup:
        print('\nПОВТОРЫ якоря между площадками:')
        for a, ds in dup.items():
            print('   «%s» -> %s' % (a, ', '.join(ds)))
    n = 0
    for j in jobs:
        if j['donor'] in res and res[j['donor']]['anchor'] != j['anchor']:
            j['anchor_prev'] = j['anchor']
            j['anchor'] = res[j['donor']]['anchor']
            j['anchor_why'] = res[j['donor']]['why']
            n += 1
    with open('final-jobs.jsonl', 'w', encoding='utf-8') as f:
        for j in jobs:
            f.write(json.dumps(j, ensure_ascii=False) + '\n')
    print('\nподобрано: %d | изменено: %d' % (len(res), n))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
