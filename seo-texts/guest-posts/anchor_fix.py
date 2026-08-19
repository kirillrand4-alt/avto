#!/usr/bin/env python3
"""Фаза 6: якоря из живых запросов, а не из синтезированных слотов.

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
Подбери текст якоря для каждой ссылки. Страницы уже назначены и НЕ меняются.

Ниже по каждой паре: площадка, тип статьи, её заголовок, целевая страница и запросы
этой страницы тремя срезами.

Как выбирать:
1. **Тематические статьи** — якорь из живых запросов, предпочтительно из полосы
   «дотягиваемые» (позиции 8-30): именно их ссылка поднимает. Якорь должен читаться
   как фраза в тексте, а не как строка из поиска: «винтовые компрессоры для
   производства» вместо «винтовой компрессор купить цена». Падеж согласуй с фразой.
2. **Жанровые статьи** (площадка не про промышленность) — только брендовый
   («Компрессор Центр», «BERG», «ENGER», «ABAC», «Atlas Copco») или безанкорный
   (домен). Коммерческий якорь там завернёт редактор.
3. Для страниц под Яндекс бери запрос из яндексового среза.
4. Не повторяй один и тот же якорь на разных площадках — ссылочный профиль должен
   быть разнообразным.
5. Якорь — 2-5 слов. Не предложение.

=== ПАРЫ ===
{pairs}

=== ФОРМАТ ОТВЕТА (строго, plain text, одна строка на донора, без markdown) ===
<донор> | <текст якоря> | <из какого среза взят и почему>
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


def main():
    cards, v15, pq, sem, th = load()
    pages = {(r['site'], r['page'].rstrip('/')): r
             for r in json.load(open('plan-queries.json', encoding='utf-8'))}
    jobs = [json.loads(l) for l in open('final-jobs.jsonl', encoding='utf-8') if l.strip()]
    jobs = [j for j in jobs if not j.get('error')]
    blocks = []
    for j in jobs:
        site, path = j['url'].replace('https://', '').split('/', 1)
        p = pages.get((site, '/' + path.rstrip('/')), {})
        b = [f"* {j['donor']} ({j['mode']}) -> {j['url']}",
             f"    статья: {j.get('title', '')}",
             f"    текущий якорь: {j['anchor']}"]
        if p:
            b.append(f"    запросов у страницы всего: {p.get('queries_total', '?')}")
            for key, title, lim in (('anchors_reach', 'ДОТЯГИВАЕМЫЕ (позиции 8-30)', 8),
                                    ('anchors_top', 'топ по показам', 5),
                                    ('anchors_yandex', 'яндексовый срез', 5)):
                s = srez(p, key, title, lim)
                if s:
                    b.append(s)
        else:
            row = next((r for r in v15 if r['site'] == site
                        and r['page'].rstrip('/') == '/' + path.rstrip('/')), None)
            anc = [a for a in ((row or {}).get('anchors') or {}).values() if a]
            b.append('    живых запросов нет (новая страница), слоты плана: ' + ' | '.join(anc))
        blocks.append('\n'.join(b))
    prompt = PROMPT.format(decisions=decisions(), pairs='\n\n'.join(blocks))
    print('пар:', len(jobs), '| промпт', len(prompt), 'символов', flush=True)
    msg = gp.call(None, [{'role': 'user', 'content': prompt}], model='claude-fable-5', attempts=4)
    raw = ''.join(b.text for b in msg.content if b.type == 'text').strip().replace('*', '')
    known = {j['donor'] for j in jobs}
    res = {}
    for line in raw.split('\n'):
        parts = [p.strip() for p in line.split('|')]
        if len(parts) >= 2 and parts[0] in known and parts[1]:
            res[parts[0]] = {'anchor': parts[1], 'why': parts[2] if len(parts) > 2 else ''}
    json.dump(res, open(OUT, 'w'), ensure_ascii=False, indent=1)
    n = 0
    for j in jobs:
        if j['donor'] in res and res[j['donor']]['anchor'] != j['anchor']:
            j['anchor_old'] = j['anchor']
            j['anchor'] = res[j['donor']]['anchor']
            j['anchor_why'] = res[j['donor']]['why']
            n += 1
    with open('final-jobs.jsonl', 'w', encoding='utf-8') as f:
        for j in jobs:
            f.write(json.dumps(j, ensure_ascii=False) + '\n')
    print('подобрано: %d | изменено: %d\n' % (len(res), n))
    for j in sorted(jobs, key=lambda x: x['mode']):
        old = f"  (было: {j['anchor_old']})" if j.get('anchor_old') else ''
        print('  %-28s %-11s %-34s%s' % (j['donor'], j['mode'], j['anchor'][:34], old[:44]))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
