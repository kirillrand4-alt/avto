# -*- coding: utf-8 -*-
"""Выборочная оценка ценности медиа-файлов КП через vision API (~$5 бюджет).
Случайная выборка jpg/png (+psd через ImageMagick, если есть), пачки по 8, effort=low.
Выход: media-sample-report.md с агрегатом по ценности."""
import json, os, random, re, subprocess, sys, base64
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_provider as gp
from kp_pipeline import drop_list, U, TOK

DIR = os.path.dirname(os.path.abspath(__file__))
SAMP = os.path.join(DIR, 'kp-work', 'media-sample')
os.makedirs(SAMP, exist_ok=True)
BUDGET_CALLS = 16          # ~16 пачек по 8 = 128 картинок; по замеру ~$0.2/пачка + запас

media = [f['name'] for f in drop_list()
         if f['name'].startswith('kp') and f['name'].rsplit('.', 1)[-1].lower()
         in ('jpg', 'jpeg', 'png')]
rnd = random.Random(42)
sample = rnd.sample(media, min(BUDGET_CALLS * 8, len(media)))
print(f'медиа всего: {len(media)} | в выборке: {len(sample)}', flush=True)

def dl(n):
    p = os.path.join(SAMP, n)
    if not os.path.exists(p):
        subprocess.run(['curl', '-s', '-H', f'X-Drop-Token: {TOK}', f'{U}/{n}', '-o', p], timeout=120)
    # ужать до 1024px для экономии токенов, если есть ImageMagick
    small = p + '.small.jpg'
    if os.path.exists(small):
        return small
    try:
        r = subprocess.run(['convert', p, '-resize', '1024x1024>', '-quality', '80', small],
                           capture_output=True, timeout=60)
        if r.returncode == 0 and os.path.exists(small):
            return small
    except FileNotFoundError:
        pass                                   # ImageMagick нет - шлём оригинал
    return p

client = gp.make_client()
results = []
batches = [sample[i:i+8] for i in range(0, len(sample), 8)]
spent_in = spent_out = 0
for bi, batch in enumerate(batches, 1):
    content = []
    ok_files = []
    for n in batch:
        try:
            p = dl(n)
            if os.path.getsize(p) > 4_500_000: continue
            ext = 'jpeg' if p.endswith(('.jpg', '.jpeg')) or p.endswith('.small.jpg') else 'png'
            content.append({'type': 'text', 'text': f'--- {n[:60]}'})
            content.append({'type': 'image', 'source': {'type': 'base64', 'media_type': f'image/{ext}',
                            'data': base64.b64encode(open(p, 'rb').read()).decode()}})
            ok_files.append(n)
        except Exception:
            continue
    if not ok_files: continue
    content.append({'type': 'text', 'text':
        'Для КАЖДОГО файла одна строка строго:\n'
        '<имя> | <тип: шильдик_со_спеками|таблица_характеристик|схема_чертёж|фото_товара|фото_с_объекта|'
        'маркетинг|сертификат|логотип_дизайн|прочее> | <данные для базы знаний: да/нет> | '
        '<ценность как фото для сайта/статей: высокая/средняя/нет> | <кратко что видно>'})
    try:
        msg = gp.call(client, [{'role': 'user', 'content': content}], model='claude-fable-5', effort='low')
        out = ''.join(b.text for b in msg.content if b.type == 'text')
        spent_in += msg.usage.input_tokens; spent_out += msg.usage.output_tokens
        results.append(out)
        print(f'пачка {bi}/{len(batches)}: {len(ok_files)} img | суммарно ~${spent_in*10/1e6+spent_out*50/1e6:.2f}', flush=True)
    except Exception as e:
        print(f'пачка {bi} сбой: {e!r}'[:120], flush=True)
    if spent_in*10/1e6 + spent_out*50/1e6 > 4.5:
        print('бюджет ~$5 достигнут, стоп', flush=True); break

txt = '\n'.join(results)
open(os.path.join(DIR, 'media-sample-raw.txt'), 'w').write(txt)
# агрегат
import collections
types = collections.Counter(); kb = collections.Counter(); val = collections.Counter()
for line in txt.splitlines():
    parts = [p.strip() for p in line.split('|')]
    if len(parts) >= 4 and parts[0].startswith('kp'):
        types[parts[1][:24]] += 1; kb[parts[2][:6]] += 1; val[parts[3][:10]] += 1
rep = [f'# Оценка медиа КП (выборка {sum(types.values())} из {len(media)})\n',
       f'Потрачено ≈ ${spent_in*10/1e6+spent_out*50/1e6:.2f} (вход {spent_in}, выход {spent_out})\n',
       f'## Типы\n' + '\n'.join(f'- {k}: {v}' for k, v in types.most_common()),
       f'\n## Данные для базы знаний\n' + '\n'.join(f'- {k}: {v}' for k, v in kb.most_common()),
       f'\n## Ценность как фото для сайта/статей\n' + '\n'.join(f'- {k}: {v}' for k, v in val.most_common())]
open(os.path.join(DIR, 'media-sample-report.md'), 'w').write('\n'.join(rep))
print('=> media-sample-report.md', flush=True)
