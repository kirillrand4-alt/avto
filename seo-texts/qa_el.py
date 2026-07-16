# -*- coding: utf-8 -*-
"""QA пилота электрических страниц: потекстовые проверки + уникальность против
пилота и дизельной партии + FAQ-повторы."""
import glob, itertools, json, re
from collections import Counter

import sys

import qa_text

PATTERN = sys.argv[1] if len(sys.argv) > 1 else 'gen/result-el-*.json'

proj_urls = set(r['url'].replace('https://prokompressor.ru', '')
                for r in json.load(open('projects-index.json')) if not r.get('error'))

results = {}
for f in sorted(glob.glob(PATTERN)):
    d = json.load(open(f))
    import os
    payload = json.load(open('gen/payload-el-' + os.path.basename(f).replace('result-el-', '')))
    issues = qa_text.check(d, min_price=payload['price_min'], price_known=True,
                           expected_h1=payload['h1'], proj_urls=proj_urls)
    # электрика: id аккордеона должны быть accordion-el-<slug>-N
    if f'accordion-el-{d["slug"]}-1' not in d['text_html']:
        issues.append('id аккордеона не по шаблону accordion-el-<slug>-N')
    # число в title должно быть точным el_count (если count_in_title)
    if d.get('title') and payload.get('count_in_title') and payload.get('el_count'):
        if str(payload['el_count']) not in d['title'].replace(' ', '').replace(' ', ''):
            issues.append(f'в title нет точного числа позиций {payload["el_count"]}')
    text = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', d['text_html'])).strip()
    results[d['slug']] = {'issues': issues, 'len': len(text), 'text': text.lower(),
                          'title': d['title'],
                          'faq': re.findall(r'<span>([^<]{10,120}\?)</span>', d['text_html'])}

def shingles(t, n=5):
    w = re.findall(r'[а-яёa-z0-9]+', t)
    return set(tuple(w[i:i + n]) for i in range(len(w) - n + 1))

sh = {s: shingles(r['text']) for s, r in results.items()}
# дизельная партия для перекрёстной проверки
diesel = {}
for f in sorted(glob.glob('gen/result-*.json')):
    if '/result-el-' in f: continue
    d = json.load(open(f))
    diesel[d['slug']] = shingles(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', d['text_html'])).lower())

print('=== ПРОБЛЕМЫ ПО ТЕКСТАМ ===')
ok = 0
for s, r in results.items():
    if r['issues']:
        print(f'\n{s}:')
        for i in r['issues']: print('   -', i)
    else:
        ok += 1
print(f'\nчистых: {ok}/{len(results)}')

print('\n=== ПОХОЖЕСТЬ ВНУТРИ ПИЛОТА (>0.12) ===')
for a, b in itertools.combinations(results, 2):
    j = len(sh[a] & sh[b]) / len(sh[a] | sh[b])
    if j > 0.12: print(f'   {a} ~ {b}: {j:.3f}')

print('\n=== ПОХОЖЕСТЬ С ДИЗЕЛЬНОЙ ПАРТИЕЙ (>0.10) ===')
for a in results:
    for b, shb in diesel.items():
        j = len(sh[a] & shb) / len(sh[a] | shb)
        if j > 0.10: print(f'   el-{a} ~ diz-{b}: {j:.3f}')

print('\n=== FAQ ===')
faqc = Counter(q for r in results.values() for q in r['faq'])
for q, c in faqc.most_common(6):
    if c > 1: print(f'   {c}×  {q}')
print(f'   уникальных вопросов: {len(faqc)} из {sum(faqc.values())}')

print('\n=== TITLES ===')
for s, r in results.items(): print(f'   {s}: {r["title"]}')
