# -*- coding: utf-8 -*-
r"""Вход агентам-исследователям: компании списка без подтверждённого сайта (нет сайта; ИНН компании на
сайте нет и модель сказала «другая»/«неясно»). Выход: <набор>-glubokiy-vhod.json на дроп."""
import io
import json
import os
import sys

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
НАБОР = os.environ.get('KC_NABOR', 'poisk')
import meyer_nalichie as MN  # noqa: E402

сп = json.load(io.open(os.path.join(DIR, НАБОР + '-spisok.json'), encoding='utf-8'))['компании']
конт, пров = {}, {}
for s in io.open(os.path.join(DIR, НАБОР + '-kontakty.jsonl'), encoding='utf-8', errors='replace'):
    з = json.loads(s)
    if з.get('итог') == 'ok':
        конт[з['inn']] = з
for s in io.open(os.path.join(DIR, НАБОР + '-sayt-proverka.jsonl'), encoding='utf-8', errors='replace'):
    з = json.loads(s)
    пров[(з['inn'], MN.домен(з.get('сайт') or ''))] = з.get('итог')
# опровергатели (kc_oproverzhenie, план Meyer п. 3.1): «опровергаю» — сайт не её, даже если ИНН на нём есть
опров = {}
if os.path.exists(os.path.join(DIR, НАБОР + '-oprov.jsonl')):
    for s in io.open(os.path.join(DIR, НАБОР + '-oprov.jsonl'), encoding='utf-8', errors='replace'):
        з = json.loads(s)
        опров[(з['inn'], MN.домен(з.get('сайт') or ''))] = з.get('итог')
вход = {}
for i, к in сп.items():
    з = конт.get(i) or {}
    сайт = з.get('сайт') or ''
    if сайт and опров.get((i, MN.домен(сайт))) == 'опровергаю':
        вход[i] = {'отклонены': MN.домен(сайт) + ' (опровергнут: сайт не её)'}
        continue
    if сайт and i in (з.get('инн_живой') or []):
        continue
    if not i.isdigit() and (сайт or к.get('сайт')):
        continue  # BY/«САЙТ:» — компания определена своим сайтом
    if сайт and пров.get((i, MN.домен(сайт))) in ('та же', 'группа'):
        continue
    вход[i] = {'отклонены': MN.домен(сайт) if сайт else ''}
with io.open(os.path.join(r'C:\seostat\drop\drop-storage', НАБОР + '-glubokiy-vhod.json'), 'w', encoding='utf-8') as f:
    json.dump(вход, f, ensure_ascii=False)
print('готово', len(вход), flush=True)
