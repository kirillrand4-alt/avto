"""Профиль раздела каталога: про что раздел (для точного выбора цели перелинковки).

  python3 cat_profile.py fetch   -> cat-raw.jsonl: товары со страницы (названия), начало
                                    текста раздела, крошки (повторный заход на раздел)
  python3 cat_profile.py profile -> cat-profile.jsonl: провайдер пачками по 25 разделов пишет
        srez (тип/бренд/давление/производительность - чем задан раздел), prodaet (что
        продаётся), zadachi (для чего), otlichie (чем отличается от соседних/родителя).
Данные payload (gen/payload-*.json: category, page_brand, цены, sample_models) подмешиваются.
"""
import concurrent.futures as cf
import glob
import json
import os
import re
import sys
import threading
import time

import requests
from bs4 import BeautifulSoup

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(DIR))
import gen_provider as GP  # noqa: E402
from link_inventory import products  # noqa: E402

SITE = 'https://prokompressor.ru'
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'}
LOCK = threading.Lock()
P = lambda n: os.path.join(DIR, n)  # noqa: E731


def jl(name):
    return [json.loads(l) for l in open(P(name), encoding='utf-8')] if os.path.exists(P(name)) else []


def append(name, rec):
    with LOCK, open(P(name), 'a', encoding='utf-8') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')
        f.flush(); os.fsync(f.fileno())


def live_cats():
    return [r for r in jl('categories.jsonl') if r.get('status') == 200 and not r.get('noindex')
            and r.get('h1') and (not r.get('final_url') or r['final_url'] == r['url'])
            and (not r.get('canonical') or r['canonical'] == r['url']) and r['url'] != '/catalog/']


def st_fetch():
    prod = products()
    done = {r['url'] for r in jl('cat-raw.jsonl')}
    todo = [r['url'] for r in live_cats() if r['url'] not in done]
    print('к заходу', len(todo), flush=True)

    def one(path):
        for i in range(3):
            try:
                time.sleep(0.3)
                r = requests.get(SITE + path, headers=UA, timeout=30)
                break
            except Exception:
                time.sleep(3)
        else:
            return
        s = BeautifulSoup(r.text, 'lxml')
        names = []
        for a in s.find_all('a', href=True):
            href = re.sub(r'^https?://[^/]+', '', a['href']).split('?')[0]
            if href in prod:
                t = a.get('title') or a.get_text(' ', strip=True)
                if t and len(t) > 6 and t not in names:
                    names.append(t[:120])
        for t in s(['script', 'style', 'noscript', 'nav', 'header', 'footer']):
            t.decompose()
        txt = ''
        h1 = s.find('h1')
        if h1:
            ps = [p.get_text(' ', strip=True) for p in h1.find_all_next('p', limit=12)]
            txt = ' '.join(p for p in ps if len(p) > 60)[:1500]
        append('cat-raw.jsonl', {'url': path, 'products': names[:15], 'text': txt})

    with cf.ThreadPoolExecutor(4) as ex:
        list(ex.map(one, todo))
    print('готово', len(jl('cat-raw.jsonl')))


PROMPT = """Ниже разделы каталога prokompressor.ru (промышленные компрессоры, осушители,
генераторы азота/кислорода, пневмооборудование). Для каждого опиши, ПРО ЧТО раздел -
чтобы при перелинковке из статей блога выбрать самый точный раздел.
Поля:
 srez - чем задан раздел (тип оборудования + фильтр: бренд / давление / производительность /
        привод / исполнение / отрасль), кратко, например «винтовые, бренд Enger, 10 бар»;
 prodaet - что конкретно в нём продаётся (по товарам), 1 строка;
 zadachi - для каких задач/отраслей/вопросов читателя этот раздел - правильный следующий шаг;
 otlichie - чем отличается от родителя/соседних срезов (если это узкий фильтр - так и скажи).
Только по данным ниже, без домыслов. Ответ строго JSON:
{{"p":[{{"url":"...","srez":"...","prodaet":"...","zadachi":"...","otlichie":"..."}}]}}

{rows}"""


def st_profile():
    cats = {r['url']: r for r in live_cats()}
    raw = {r['url']: r for r in jl('cat-raw.jsonl')}
    pay = {}
    for f in glob.glob(os.path.join(os.path.dirname(DIR), 'gen', 'payload-*.json')):
        d = json.load(open(f, encoding='utf-8'))
        pay[d['url']] = d
    done = {r['url'] for r in jl('cat-profile.jsonl')}
    todo = [u for u in sorted(cats) if u not in done and u in raw]

    def row(u):
        c, r, d = cats[u], raw[u], pay.get(u, {})
        bits = [f"URL: {u}", f"H1: {c['h1']}", f"Крошки: {' > '.join(c.get('crumbs', []))}",
                f"Товаров на странице: {c.get('n_products', 0)}",
                f"Товары: {'; '.join(r['products'][:12])}"]
        if d:
            bits.append(f"Payload: категория {d.get('category')}, бренд {d.get('page_brand')}, "
                        f"цены {d.get('price_min')}-{d.get('price_max')}, модели {str(d.get('sample_models'))[:300]}")
        if r.get('text'):
            bits.append(f"Текст: {r['text'][:600]}")
        return '\n'.join(bits)

    def batch(us):
        try:
            m = GP.call(None, [{'role': 'user', 'content': PROMPT.format(rows='\n\n'.join(row(u) for u in us))}],
                        model='claude-opus-5-5', thinking_on=False, max_tokens=8000)
            txt = m if isinstance(m, str) else ''.join(b.text for b in m.content if b.type == 'text')
            res = json.loads(re.search(r'\{.*\}', txt, re.S).group(0))
        except Exception as e:
            print('ERR', us[0], repr(e)[:120], flush=True)
            return
        for p in res.get('p', []):
            if p.get('url') in cats:
                append('cat-profile.jsonl', p)

    with cf.ThreadPoolExecutor(4) as ex:
        list(ex.map(batch, [todo[i:i + 25] for i in range(0, len(todo), 25)]))
    print('профилей', len(jl('cat-profile.jsonl')))


if __name__ == '__main__':
    {'fetch': st_fetch, 'profile': st_profile}[sys.argv[1]]()
