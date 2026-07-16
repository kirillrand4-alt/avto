# -*- coding: utf-8 -*-
"""Извлечение фактов из брендовых страниц prokompressor.ru (канал 2) через Fable API +
предложение официального домена с уверенностью (для решения, нужен ли мой веб-поиск)."""
import glob, json, re, os
from concurrent.futures import ThreadPoolExecutor, as_completed
from gen_provider import make_client, call

files = sorted(glob.glob('kb/brand-pages-raw/*.html'))

def clean(h):
    h = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', h, flags=re.S)
    h = re.sub(r'<[^>]+>', ' ', h)
    return re.sub(r'\s+', ' ', h).strip()

PROMPT = """Это текст брендовой страницы бренда «{slug}» с сайта магазина компрессоров prokompressor.ru.
Извлеки факты О БРЕНДЕ (не о магазине). Текст:
{text}

Верни ОДИН JSON:
- brand: название
- from_page: {{"country":"", "founded":"", "positioning":"", "product_lines":[], "tech_facts":[], "rf_presence":""}}
  (только то, что реально сказано на странице; пусто если нет)
- official_domain_guess: твоё предположение официального сайта производителя (только домен)
- domain_confidence: high (уверен точно) / medium / low (не знаю - нужен веб-поиск)
- notes: расхождения, сомнительные заявления, на что обратить внимание"""

client = make_client()
def worker(f):
    slug = os.path.basename(f)[:-5]
    text = clean(open(f, encoding='utf-8', errors='ignore').read())[:9000]
    if len(text) < 300:
        return {'brand': slug, 'error': 'пустая страница', 'domain_confidence': 'low'}
    msg = call(client, [{'role':'user','content':PROMPT.format(slug=slug, text=text)}], 'claude-fable-5')
    t = ''.join(b.text for b in msg.content if b.type=='text')
    m = re.search(r'\{.*\}', t, re.S)
    res = json.loads(m.group(0)); res['_slug'] = slug
    print(f'ок: {slug} (домен: {res.get("domain_confidence")})', flush=True)
    return res

results = []
with ThreadPoolExecutor(max_workers=8) as ex:
    futs = {ex.submit(worker, f): f for f in files}
    for fu in as_completed(futs):
        try: results.append(fu.result())
        except Exception as e: print(f'FAIL {futs[fu]}: {repr(e)[:90]}', flush=True)
json.dump(results, open('kb/brand-pages-facts.json','w'), ensure_ascii=False, indent=1)
lo = [r['_slug'] for r in results if r.get('domain_confidence')=='low']
print(f'ИЗВЛЕЧЕНО: {len(results)} | нужен веб-поиск домена для {len(lo)}: {lo}')
