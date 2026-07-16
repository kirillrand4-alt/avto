# -*- coding: utf-8 -*-
"""Вся батарея ревьюеров (филолог + инженер + Яндекс + Google) на ОДНИХ И ТЕХ ЖЕ случайных 50
страницах из всех 759 (уже с перегенерированными). Каждая персона идёт 5 пачками по 10.
Прогон через провайдер (raw-SSE call, устойчив). Свод в review-all-50.md."""
import json, os, re, random, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
import gen_provider as gp
from review_philolog import PERSONA as PHILOLOG
from review_engineer import PERSONA as ENGINEER
from review_seo import YANDEX, GOOGLE

DIR = os.path.dirname(os.path.abspath(__file__))
MODEL = 'claude-fable-5'
PERSONAS = [('Филолог (по-русски)', PHILOLOG), ('Инженер (тех. точность)', ENGINEER),
            ('Яндекс (ранжирование Рунет)', YANDEX), ('Google (Helpful Content 2026)', GOOGLE)]
BATCH_NOTE = ('\n\nВАЖНО: это ПАЧКА из 10 текстов. Пройдись по КАЖДОМУ, укажи категорию/H1 и находки '
              '(или «чисто»). В конце — короткий общий вывод по пачке: что опасно/вредно, что полезно, '
              'чего не хватает.\n\n=== 10 ТЕКСТОВ ===\n')


def readable(slug):
    d = json.load(open(os.path.join(DIR, f'gen/result-{slug}.json')))
    p = json.load(open(os.path.join(DIR, f'gen/payload-{slug}.json')))
    txt = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', d['text_html']).replace('&nbsp;', ' ')).strip()
    return f'### ID {slug} [{p.get("category")}] {p.get("h1")}\n{txt}\n'


def one(persona_name, persona, bi, slugs, client):
    corpus = '\n\n'.join(readable(s) for s in slugs)
    try:
        msg = gp.call(client, [{'role': 'user', 'content': persona + BATCH_NOTE + corpus}], model=MODEL)
        out = ''.join(b.text for b in msg.content if b.type == 'text').strip()
    except Exception as e:
        out = f'[пачка {bi} не удалась: {e!r}]'
    return persona_name, bi, out


def main():
    allslugs = sorted(os.path.basename(f)[len('result-'):-len('.json')]
                      for f in os.listdir(os.path.join(DIR, 'gen')) if f.startswith('result-'))
    rnd = random.Random(int(os.environ.get('SEED', '2026')))
    sample = rnd.sample(allslugs, 50)
    open(os.path.join(DIR, 'review-all-50-sample.txt'), 'w').write('\n'.join(sample) + '\n')
    batches = [sample[i:i + 10] for i in range(0, 50, 10)]
    client = gp.make_client()
    tasks = [(pn, p, bi, b) for (pn, p) in PERSONAS for bi, b in enumerate(batches, 1)]
    results = {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(one, pn, p, bi, b, client): (pn, bi) for pn, p, bi, b in tasks}
        for f in as_completed(futs):
            pn, bi, out = f.result()
            results[(pn, bi)] = out
            print(f'готово: {pn} пачка {bi}/5 ({len(out)} зн.)', flush=True)
    lines = ['# Батарея ревьюеров — случайные 50 страниц из всех 759\n',
             f'Выборка (seed): review-all-50-sample.txt | модель {MODEL}\n']
    for pn, _ in PERSONAS:
        lines.append(f'\n\n# {pn}\n')
        for bi in range(1, 6):
            lines.append(f'\n## Пачка {bi}\n\n{results.get((pn, bi), "—")}')
    open(os.path.join(DIR, 'review-all-50.md'), 'w', encoding='utf-8').write('\n'.join(lines))
    print('свод: review-all-50.md')


if __name__ == '__main__':
    main()
