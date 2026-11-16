#!/usr/bin/env python3
"""Принципы 2-3 по позициям доноров (donory-pozicii.jsonl) - разметка через провайдерский API.

Модель размечает каждую строку (запрос + URL): тема (prom - промышленное оборудование/
производство/инженерия, smezh - стройка/техника/бизнес, mimo - остальное), тип страницы
(statya - статья/публикация/материал компании, katalog, novost, spravka, glavnaya, prochee),
токсичность (казино/ставки/кредиты/фарма/взрослое). Доли трафика считает скрипт.
Выход: donory-klass.jsonl (резюмируемо, fsync).
"""
import json
import os
import re
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(DIR))
import gen_provider as GP  # noqa: E402

OUT = os.path.join(DIR, 'donory-klass.jsonl')
PROMPT = """Размечаешь поисковую видимость сайта-донора для закупки ссылки промышленной компанией
(компрессоры, генераторы азота, промышленное оборудование). Ниже строки: N | запрос | URL | трафик.
Для каждой строки верни метки:
 t: prom (промышленное оборудование, производство, инженерия, металлы, энергетика),
    smezh (стройка, ремонт, техника, авто, бизнес, B2B), mimo (всё остальное);
 p: statya (статья, публикация, обзор, материал компании, пресс-релиз), katalog (каталог,
    карточка компании/товара), novost, spravka (справочник, ГОСТ, цены, таблицы), glavnaya, prochee;
 x: 1 если казино/ставки/слоты/кредиты/микрозаймы/фарма/взрослое, иначе 0.
Ответ строго JSON без пояснений: {"rows":[[N,"t","p",x],...],"razdel_statej":"путь раздела, где
выходят статьи/публикации компаний, если виден по URL, иначе пусто"}
"""


def label(dom, rows):
    lines = '\n'.join(f'{i} | {r[0]} | {r[1]} | {r[2]}' for i, r in enumerate(rows))
    txt = GP.call(None, [{'role': 'user', 'content': PROMPT + f'\nСайт: {dom}\n' + lines}],
                  model='claude-opus-5-5', thinking_on=False, max_tokens=8000)
    txt = txt if isinstance(txt, str) else ''.join(b.text for b in txt.content if b.type == 'text')
    return json.loads(re.search(r'\{.*\}', txt, re.S).group(0))


def main():
    done = set()
    if os.path.exists(OUT):
        done = {json.loads(l)['domain'] for l in open(OUT, encoding='utf-8')}
    with open(OUT, 'a', encoding='utf-8') as f:
        for l in open(os.path.join(DIR, 'donory-pozicii.jsonl'), encoding='utf-8'):
            d = json.loads(l)
            if d.get('error') or d['domain'] in done or not d.get('rows'):
                continue
            rows = d['rows']
            lab = label(d['domain'], rows)
            m = {int(x[0]): x for x in lab['rows'] if isinstance(x, list) and len(x) >= 4}
            tot = sum(r[2] or 0 for r in rows) or 1
            sh = lambda cond: round(sum((r[2] or 0) for i, r in enumerate(rows) if i in m and cond(m[i])) / tot, 2)  # noqa: E731
            st_rows = [r for i, r in enumerate(rows) if i in m and m[i][2] == 'statya']
            rec = {'domain': d['domain'], 'traffic_top': tot,
                   'prom': sh(lambda x: x[1] == 'prom'), 'prom_smezh': sh(lambda x: x[1] in ('prom', 'smezh')),
                   'statya': sh(lambda x: x[2] == 'statya'), 'toxic': sh(lambda x: int(x[3]) == 1),
                   'statya_prom': sh(lambda x: x[2] == 'statya' and x[1] in ('prom', 'smezh')),
                   'razdel': lab.get('razdel_statej', ''),
                   'top_statyi': [[r[0], r[1], r[2]] for r in st_rows[:5]]}
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
            print(rec['domain'], {k: rec[k] for k in ('prom', 'prom_smezh', 'statya', 'statya_prom', 'toxic')},
                  rec['razdel'], flush=True)


if __name__ == '__main__':
    main()
