#!/usr/bin/env python3
"""Фаза 5: развести пересекающиеся углы — один агент видит все джобы разом.

Финальная сборка (`final_jobs.py`) идёт по донорам параллельно, и агенты не знают
друг о друге. На похожих страницах это даёт близнецов: четыре статьи вышли как
«Подбор винтового компрессора для производственного цеха» — для ess-ltd.ru, fgisrf.ru,
galan.ru и factories.kz, потому что у всех четырёх целевая страница про винтовые
компрессоры, просто на разных сайтах.

Публиковать такие тексты по разным площадкам нельзя: читателю скучно, поисковику
видно штамповку, а редактор второй площадки может узнать первую статью.

Здесь агент видит ВСЕ 24 угла сразу и переписывает только пересекающиеся — под
аудиторию конкретной площадки. Страницы и якоря не трогает: они уже назначены.

    python3 dedup_jobs.py
"""
from __future__ import annotations

import json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gen_provider as gp                                    # noqa: E402
from plan_jobs import decisions                              # noqa: E402

OUT = os.environ.get('DEDUP_OUT', 'dedup.json')

PROMPT = """=== РЕШЕНИЯ ВЛАДЕЛЬЦА (приоритет выше любых расчётов) ===
{decisions}

=== ЗАДАЧА ===
Ниже 24 задания на гостевые статьи. Каждое писалось отдельно, поэтому часть углов
получилась близнецами — на похожих целевых страницах агенты пришли к одной теме.

Найди пересечения и разведи их. Статьи выходят на РАЗНЫХ площадках, у каждой своя
аудитория — угол должен идти от неё, а не от товара. Четыре текста «подбор винтового
компрессора для цеха» на четырёх площадках недопустимы.

Правила:
1. Страницу и якорь НЕ меняй — они назначены отдельным решением.
2. Переписывай ТОЛЬКО те задания, что пересекаются с другими. Уникальные оставь как есть.
3. Новый угол должен идти от аудитории площадки: у монтажников вентиляции, у аграриев,
   у автосервиса, у строителей — разные задачи, даже если товар один.
4. Тема обязана оставаться честной для целевой страницы: если ссылка ведёт на винтовые
   компрессоры, статья не может быть про генераторы азота.
5. Не выдумывай числа и факты.

=== ЗАДАНИЯ ===
{jobs}

=== ФОРМАТ ОТВЕТА (строго, plain text, без markdown) ===
Сначала строка со списком пересечений:
ПЕРЕСЕЧЕНИЯ: <донор+донор: чем похожи>; <...>

Затем — только для переписанных, по блоку на каждого:
ДОНОР: <домен>
ЗАГОЛОВОК: <новый заголовок>
УГОЛ: <новый угол, 3-5 предложений>
СКЕЛЕТ: <новая структура, разделы через ->>
ПОЧЕМУ: <одна строка: чем этот угол теперь отличается от соседнего>
---
"""


def main():
    recs = [json.loads(l) for l in open('final-jobs.jsonl', encoding='utf-8') if l.strip()]
    recs = [r for r in recs if not r.get('error')]
    jobs = []
    for r in recs:
        jobs.append(
            f"* {r['donor']} ({r['mode']}) -> {r['url']}\n"
            f"  площадка: {(r.get('donor_note') or '')[:150]}\n"
            f"  заголовок: {r.get('title', '')}\n"
            f"  угол: {(r.get('angle') or '')[:330]}")
    prompt = PROMPT.format(decisions=decisions(), jobs='\n\n'.join(jobs))
    print('заданий:', len(recs), '| промпт', len(prompt), 'символов', flush=True)
    msg = gp.call(None, [{'role': 'user', 'content': prompt}], model='claude-fable-5', attempts=4)
    raw = ''.join(b.text for b in msg.content if b.type == 'text').strip().replace('*', '')
    inter = (re.search(r'ПЕРЕСЕЧЕНИЯ:\s*(.+)', raw) or [None, ''])[1].strip()
    print('\nнайденные пересечения:', inter[:400], flush=True)
    out = []
    for block in raw.split('---'):
        g = lambda k: (re.search(rf'^{k}:\s*(.+?)(?=\n[А-ЯA-Z][А-ЯA-Z ]{{2,}}:|\Z)',
                                 block, re.S | re.M) or [None, ''])[1].strip()
        dom = g('ДОНОР')
        if dom and g('УГОЛ'):
            out.append({'donor': dom, 'title': g('ЗАГОЛОВОК'), 'angle': g('УГОЛ'),
                        'skeleton': g('СКЕЛЕТ'), 'why': g('ПОЧЕМУ')})
    json.dump({'intersections': inter, 'rewritten': out}, open(OUT, 'w'),
              ensure_ascii=False, indent=1)
    print('\nпереписано заданий:', len(out))
    for r in out:
        print('  %-28s %s' % (r['donor'], r['title'][:64]))
    # Правки вносим в сами джобы: генератор читает их, а не этот файл.
    by = {r['donor']: r for r in out}
    n = 0
    for r in recs:
        if r['donor'] in by:
            u = by[r['donor']]
            r['title_old'], r['angle_old'] = r.get('title'), r.get('angle')
            r['title'], r['angle'] = u['title'], u['angle']
            if u['skeleton']:
                r['skeleton_old'], r['skeleton'] = r.get('skeleton'), u['skeleton']
            r['dedup_why'] = u['why']
            n += 1
    with open('final-jobs.jsonl', 'w', encoding='utf-8') as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print('обновлено джоб:', n)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
