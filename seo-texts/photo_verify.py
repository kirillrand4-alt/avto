# -*- coding: utf-8 -*-
"""Контрольная проверка models_visible фотобанка: те же фото БЕЗ имён файлов.
Вопрос: какие модели читаются НЕПОСРЕДСТВЕННО на изображении?
Вердикты: подтверждено / другая_модель / не_читается (наведено именем файла).
Выход: kb/photo-models-verify.json + сводка."""
import base64, json, os, re, sys

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)
import gen_provider as gp

RAW = os.path.join(DIR, 'media-work', 'raw')
CYR = str.maketrans('АВЕКМНОРСТУХаверкмнорстух', 'ABEKMHOPCTYXabepkmhopctyx')
def norm(s): return re.sub(r'[\s\-–—_/.]', '', str(s).translate(CYR).upper())

bank = json.load(open(os.path.join(DIR, 'kb', 'photo-bank.json')))
todo = [(n, v) for n, v in bank.items() if v.get('models_visible')
        and os.path.exists(os.path.join(RAW, v.get('file', n)))]
print(f'проверяем {len(todo)} фото с заявленными моделями', flush=True)

client = gp.make_client()
out = {}
for bi in range(0, len(todo), 6):
    batch = todo[bi:bi + 6]
    content = []
    for j, (n, v) in enumerate(batch, 1):
        p = os.path.join(RAW, v.get('file', n))
        ext = 'jpeg' if p.lower().endswith(('.jpg', '.jpeg')) else 'png'
        content.append({'type': 'text', 'text': f'--- img{j}'})
        content.append({'type': 'image', 'source': {'type': 'base64',
                        'media_type': f'image/{ext}',
                        'data': base64.b64encode(open(p, 'rb').read()).decode()}})
    content.append({'type': 'text', 'text':
        'Для КАЖДОГО изображения перечисли обозначения моделей оборудования, которые '
        'ЧИТАЮТСЯ непосредственно на самом изображении (шильдик, наклейка, маркировка '
        'на корпусе, надпись в кадре). Если ничего не читается - пустой список. '
        'НЕ угадывай по внешнему виду. Верни ТОЛЬКО JSON-массив: '
        '[{"img":"img1","models_readable":["..."]}, ...]'})
    try:
        msg = gp.call(client, [{'role': 'user', 'content': content}],
                      model='claude-fable-5', effort='low')
        arr = gp.parse_json(msg)
        got = {a['img']: a.get('models_readable', []) for a in arr}
    except Exception as e:
        print(f'  пачка {bi//6+1} сбой: {e!r}'[:100], flush=True)
        got = {}
    for j, (n, v) in enumerate(batch, 1):
        readable = got.get(f'img{j}', None)
        claimed = v['models_visible']
        if readable is None:
            verdict = 'сбой'
        elif not readable:
            verdict = 'не_читается'
        else:
            cn = {norm(c) for c in claimed}
            rn = {norm(r) for r in readable}
            verdict = ('подтверждено' if any(c in r or r in c for c in cn for r in rn if c and r)
                       else 'другая_модель')
        out[n] = dict(file=v.get('file', n), claimed=claimed, readable=readable, verdict=verdict)
    if (bi // 6) % 5 == 4:
        print(f'  {bi+6}/{len(todo)}', flush=True)

json.dump(out, open(os.path.join(DIR, 'kb', 'photo-models-verify.json'), 'w'),
          ensure_ascii=False, indent=1)
from collections import Counter
c = Counter(v['verdict'] for v in out.values())
print('ИТОГ:', dict(c), flush=True)
