# -*- coding: utf-8 -*-
"""Проверка выборки медиа на ИИ-генерацию (по уже скачанным файлам media-sample)."""
import base64, json, os, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_provider as gp

DIR = os.path.dirname(os.path.abspath(__file__))
SAMP = os.path.join(DIR, 'kp-work', 'media-sample')
files = [f for f in sorted(os.listdir(SAMP)) if not f.endswith('.small.jpg')
         and f.rsplit('.',1)[-1].lower() in ('jpg','jpeg','png')]
print(f'локальных картинок: {len(files)}', flush=True)

client = gp.make_client()
results = []
spent_in = spent_out = 0
batches = [files[i:i+8] for i in range(0, len(files), 8)]
for bi, batch in enumerate(batches, 1):
    content = []
    for n in batch:
        p = os.path.join(SAMP, n)
        sm = p + '.small.jpg'
        p = sm if os.path.exists(sm) else p
        if os.path.getsize(p) > 4_500_000: continue
        ext = 'jpeg' if p.endswith(('.jpg','.jpeg')) else 'png'
        content.append({'type':'text','text':f'--- {n[:60]}'})
        content.append({'type':'image','source':{'type':'base64','media_type':f'image/{ext}',
                        'data': base64.b64encode(open(p,'rb').read()).decode()}})
    content.append({'type':'text','text':
        'Ты эксперт по детекции ИИ-изображений. Для КАЖДОГО файла одна строка строго:\n'
        '<имя> | <вердикт: реальное_фото|ИИ_генерация|3D_рендер|фотомонтаж|скан_печати|неопределимо> | '
        '<уверенность: высокая/средняя/низкая> | <маркеры, кратко>\n'
        'Маркеры ИИ: артефакты текста/шильдиков, невозможная геометрия труб/резьбы, смазанные повторы, '
        'нефизичные тени/отражения, "пластиковые" текстуры металла. 3D-рендер (CAD) - НЕ ИИ.'})
    try:
        msg = gp.call(client, [{'role':'user','content':content}], model='claude-fable-5', effort='low')
        out = ''.join(b.text for b in msg.content if b.type=='text')
        spent_in += msg.usage.input_tokens; spent_out += msg.usage.output_tokens
        results.append(out)
        print(f'пачка {bi}/{len(batches)} | ~${spent_in*10/1e6+spent_out*50/1e6:.2f}', flush=True)
    except Exception as e:
        print(f'пачка {bi} сбой: {e!r}'[:100], flush=True)

txt = '\n'.join(results)
open(os.path.join(DIR,'media-aidetect-raw.txt'),'w').write(txt)
verd = collections.Counter(); ai_files=[]
for line in txt.splitlines():
    p=[x.strip() for x in line.split('|')]
    if len(p)>=3 and p[0].startswith('kp'):
        verd[p[1][:16]] += 1
        if 'ИИ' in p[1]: ai_files.append((p[0], p[2], p[3][:80] if len(p)>3 else ''))
rep=[f'# ИИ-детект медиа (выборка {sum(verd.values())})\n',
     '## Вердикты\n'+'\n'.join(f'- {k}: {v}' for k,v in verd.most_common()),
     '\n## Подозрения на ИИ\n'+('\n'.join(f'- {f} ({c}): {m}' for f,c,m in ai_files) if ai_files else '- не найдено')]
open(os.path.join(DIR,'media-aidetect-report.md'),'w').write('\n'.join(rep))
print('=> media-aidetect-report.md', flush=True)
