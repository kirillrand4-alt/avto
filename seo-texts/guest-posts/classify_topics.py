#!/usr/bin/env python3
"""Реальная тематика донора: решает текст площадки, а не ярлык биржи.

Владелец 05.08: «тематике особо не верь у доноров». Владелец 18.08: «там ещё могут
быть разные разделы, может раздел подходящий будет» - поэтому вердикт выносится
НЕ по сайту целиком, а по разделу, в который ляжет статья: площадка про женские
хобби с живым разделом «Строительство» нам подходит, а «промышленный» портал без
такого раздела - нет.

Вход: topic-raw.json (главная + разделы + заголовки материалов внутри разделов).
Выход: topic-verdicts.json. Модель - провайдерский API (правило владельца:
тяжёлое не жечь квотой сессии).

    python3 classify_topics.py
"""
from __future__ import annotations

import concurrent.futures as cf
import json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gen_provider as gp                                    # noqa: E402

PROMPT = """Ты - редактор, подбирающий площадки для гостевых статей поставщика
промышленного оборудования: компрессоры, компрессорные станции, генераторы азота
и кислорода, осушители сжатого воздуха. Покупатель - главный инженер, снабженец,
энергетик, прораб, владелец автосервиса или фермерского хозяйства.

Тебе дан РЕАЛЬНЫЙ снимок площадки: заголовок, описание, разделы меню и заголовки
материалов внутри разделов. Ярлык тематики с биржи не показан намеренно - его
проставляет вебмастер и он врёт.

Ответь СТРОГО в формате:
ВЕРДИКТ: наша | смежная | мимо
РАЗДЕЛ: <название раздела, в который органично ляжет статья про промышленное
оборудование, либо «нет»>
АУДИТОРИЯ: <одна строка: кто реально читает эту площадку>
ПОЧЕМУ: <одна-две строки по фактам снимка>

Критерии:
* «наша» - есть раздел, где статья про компрессорную или азотную станцию будет
  выглядеть своей: промышленность, производство, строительство, энергетика,
  агропром, автосервис, техника, деловые новости региона с промышленной повесткой.
* «смежная» - раздела под тему нет, но аудитория пересекается (например, деловое
  издание без промышленного раздела, автопортал для частников).
* «мимо» - читатель не имеет отношения к производству: развлечения, культура,
  женские темы, образование школьное, интерьеры для дома, гадания.
Отсутствие слова «компрессор» на площадке НЕ повод для «мимо»: мы приносим тему
сами. Важно, есть ли раздел и тот ли читатель.

=== СНИМОК ПЛОЩАДКИ ===
"""


def snapshot(d: dict) -> str:
    out = [f"домен: {d['domain']}", f"заголовок: {d.get('title','')}",
           f"описание: {d.get('description','')}",
           'разделы меню: ' + ', '.join(s['text'] for s in d.get('sections', [])[:30])]
    for s in (d.get('section_pages') or []):
        out.append(f"\nРАЗДЕЛ «{s['section']}» ({s['url']}):")
        out += ['  - ' + h for h in s['headlines'][:14]]
    if d.get('headlines'):
        out.append('\nзаголовки с главной:')
        out += ['  - ' + h for h in d['headlines'][:14]]
    return '\n'.join(out)


def one(client, d):
    try:
        msg = gp.call(client, [{'role': 'user', 'content': PROMPT + snapshot(d)}],
                      model='claude-fable-5')
        # call() возвращает объект сообщения, а не строку: текст лежит в блоках content
        out = ''.join(b.text for b in msg.content if b.type == 'text').strip()
    except Exception as e:                                   # noqa: BLE001
        return {'domain': d['domain'], 'error': repr(e)[:150]}
    g = lambda k: (re.search(rf'{k}:\s*(.+)', out) or [None, ''])[1].strip()
    return {'domain': d['domain'], 'verdict': g('ВЕРДИКТ').split()[0].lower() if g('ВЕРДИКТ') else '?',
            'section': g('РАЗДЕЛ'), 'audience': g('АУДИТОРИЯ'), 'why': g('ПОЧЕМУ')}


def main():
    data = json.load(open('topic-raw.json', encoding='utf-8'))
    doms = list(data.values())
    client = gp.make_client()
    res = []
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        for r in ex.map(lambda d: one(client, d), doms):
            res.append(r)
            print(f"  {r['domain']:26} {r.get('verdict','ERR'):8} {r.get('section','')[:34]}", flush=True)
    json.dump(res, open('topic-verdicts.json', 'w'), ensure_ascii=False, indent=1)
    import collections
    print('итог:', dict(collections.Counter(r.get('verdict') for r in res)))


if __name__ == '__main__':
    main()
