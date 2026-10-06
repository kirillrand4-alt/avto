# -*- coding: utf-8 -*-
"""Разметка выборки калибровки моделью через провайдерский API -> kalibr_metki.json."""
import json, os, re, sys
from concurrent.futures import ThreadPoolExecutor
D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(D, '..', '..', 'seo-texts'))
import gen_provider as G  # noqa: E402
G.env = lambda: {'PROVIDER_API_KEY': os.environ['PROVIDER_API_KEY'],
                 'PROVIDER_BASE_URL': os.environ.get('PROVIDER_BASE_URL', 'https://router.cheap')}
SRC = sys.argv[1]
OUT = os.path.join(D, 'kalibr_metki.json')
V = [v for v in json.load(open(SRC, encoding='utf-8')) if v.get('ok')]
have = json.load(open(OUT, encoding='utf-8')) if os.path.exists(OUT) else {}
PROMPT = """Ниже главные страницы сайтов. Для каждого определи, собственный ли это сайт компании, которая САМА
работает в одном из сегментов (не перепродаёт чужое, не обслуживает отрасль):
- exporters: экспортёр/трейдер зерна, масличных, бобовых, масла, шрота;
- seeds: семеновод (производит семена, семенной завод, оригинатор, семенной картофель);
- food: пищевое производство раздела 10 ОКВЭД (мука, крупа, масло, крахмал, комбикорм, консервы, соки, сахар, молочка и т.п.);
- elevators: элеватор, ХПП, КХП, зернохранение, сушка/подработка зерна как услуга;
- nuts: выращивание или переработка орехов, ореховые питомники;
- berries: ягодное хозяйство, плантация, ягодный питомник, заморозка/переработка ягод.
Не профильны: дилеры и дистрибьюторы, оптовые торговцы чужой продукцией, розница и интернет-магазины,
производители оборудования и упаковки, СМИ, каталоги, биржи, госорганы и учреждения, вузы и НИИ без производства,
консалтинг и логистика, сайты-заглушки.

Ответ — ТОЛЬКО JSON-массив в том же порядке:
[{"i":0,"profile":true|false,"segments":["seeds",...],"type":"производитель|хозяйство|переработчик|трейдер|элеватор|питомник|дилер|дистрибьютор|розница|оборудование|сми_каталог|гос_наука|услуги|другое","why":"до 8 слов"}]

"""
def batch(items):
    body = PROMPT + '\n\n'.join(
        f"### {i}. {v['domain']}\nTITLE: {v.get('title','')}\nH1: {v.get('h1','')}\nТЕКСТ: {v['text'][:1800]}"
        for i, v in enumerate(items))
    msg = G.call(None, [{'role': 'user', 'content': body}], model='claude-opus-5-5', attempts=4)
    txt = ''.join(b.text for b in msg.content if b.type == 'text')
    arr = json.loads(re.search(r'\[.*\]', txt, re.S).group(0))
    return {items[a['i']]['domain']: a for a in arr if 0 <= a.get('i', -1) < len(items)}
todo = [v for v in V if v['domain'] not in have]
chunks = [todo[i:i + 10] for i in range(0, len(todo), 10)]
with ThreadPoolExecutor(4) as ex:
    for res in ex.map(lambda c: (lambda: batch(c))() if c else {}, chunks):
        have.update(res)
        json.dump(have, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
print('размечено', len(have), 'из', len(V))
