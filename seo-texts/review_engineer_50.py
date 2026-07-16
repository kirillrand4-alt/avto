# -*- coding: utf-8 -*-
"""Инженерное ревью на 50 случайных текстах, пачками по 10 (чтобы вникать в каждый, не скользить).
Пачки идут параллельно через провайдер. Результаты сводятся в review-engineer-50.md."""
import json, os, re, random
from concurrent.futures import ThreadPoolExecutor, as_completed
import gen_provider as gp
from review_engineer import PERSONA, readable

DIR = os.path.dirname(os.path.abspath(__file__))


def review_chunk(idx, slugs, client):
    corpus = '\n\n'.join(readable(s) for s in slugs if os.path.exists(os.path.join(DIR, f'gen/result-{s}.json')))
    prompt = PERSONA + ('\n\nВАЖНО: это ПАЧКА из 10 текстов. Пройдись по КАЖДОМУ, не пропуская. '
                        'Для каждого укажи номер/категорию и найденные ошибки (или «чисто»).\n\n'
                        '=== 10 ТЕКСТОВ ===\n') + corpus
    try:
        msg = gp.call(client, [{'role': 'user', 'content': prompt}], model='claude-fable-5')
        return idx, ''.join(b.text for b in msg.content if b.type == 'text').strip()
    except Exception as e:
        return idx, f'[пачка {idx} не удалась: {e!r}]'


def main():
    allslugs = sorted(os.path.basename(f)[len('result-'):-len('.json')]
                      for f in os.listdir(os.path.join(DIR, 'gen')) if f.startswith('result-'))
    rnd = random.Random(50)          # фикс. seed для воспроизводимости
    sample = rnd.sample(allslugs, 50)
    open(os.path.join(DIR, 'eng50-sample.txt'), 'w').write('\n'.join(sample) + '\n')
    chunks = [sample[i:i + 10] for i in range(0, 50, 10)]
    client = gp.make_client()
    results = {}
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = {ex.submit(review_chunk, i, ch, client): i for i, ch in enumerate(chunks, 1)}
        for f in as_completed(futs):
            i, txt = f.result(); results[i] = txt
            print(f'пачка {i}/5 готова ({len(txt)} знаков)', flush=True)
    out = ['# Инженерное ревью — 50 случайных текстов (5 пачек по 10)\n']
    for i in sorted(results):
        out.append(f'\n\n## ПАЧКА {i}\n\n{results[i]}')
    open(os.path.join(DIR, 'review-engineer-50.md'), 'w', encoding='utf-8').write('\n'.join(out))
    print('сведено в review-engineer-50.md')


if __name__ == '__main__':
    main()
