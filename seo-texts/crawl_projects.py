# -*- coding: utf-8 -*-
import re, html as H, json, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36"
urls = [u.strip() for u in open('projects-urls.txt') if u.strip().count('/') == 6]  # depth-7 = detail pages
print('detail pages:', len(urls), file=sys.stderr)

CITY_RE = re.compile(r'(?:г\.\s*|город[ае]?\s+|в\s+городе\s+)([А-ЯЁ][а-яё-]+(?:\s[А-ЯЁ][а-яё-]+)?)')

def fetch(u):
    try:
        r = subprocess.run(['curl','-sS','--max-time','40','-A',UA,u], capture_output=True, text=True, timeout=50)
        return u, r.stdout
    except Exception as e:
        return u, ''

def parse(u, src):
    if not src or len(src) < 5000:
        return {'url': u, 'error': 'empty'}
    rec = {'url': u, 'category': u.split('/')[4]}
    m = re.search(r'<title>(.*?)</title>', src);  rec['title'] = H.unescape(m.group(1)) if m else ''
    m = re.search(r'<h1[^>]*>(.*?)</h1>', src, re.S)
    rec['h1'] = H.unescape(re.sub(r'<[^>]+>','',m.group(1)).strip()) if m else ''
    i = src.find('class="properties"')
    body = ''
    if i > 0:
        frag = src[i:i+12000]
        frag = re.sub(r'<script.*?</script>','',frag,flags=re.S)
        txt = re.sub(r'<[^>]+>','|',frag)
        txt = H.unescape(re.sub(r'\|+','|',txt))
        body = txt
        for field, pat in [('date', r'Дата проекта\|?:?\|?\s*([^|]{2,40})'),
                           ('sphere', r'Сфера\|([^|]{2,60})'),
                           ('brand', r'Производитель\|([^|]{2,60})'),
                           ('equipment', r'Оборудование:?\|([^|]{3,300})'),
                           ('client', r'Заказчик\|?:?\|?\s*([^|]{2,120})'),
                           ('service', r'Услуга\|?:?\|?\s*([^|]{2,80})')]:
            mm = re.findall(pat, txt)
            rec[field] = mm[-1].strip().strip(':').strip() if mm else ''
        # narrative: text after 'Услуга' till 'Товары|Все'
        j = txt.find('Услуга')
        k = txt.find('|Товары|')
        if j>0:
            nar = txt[j:k if k>j else j+3000]
            nar = re.sub(r'^[^|]*\|','',nar)
            rec['narrative'] = nar.replace('|',' ').strip()[:2000]
    cities = CITY_RE.findall(body)
    STOPCITY = {'Заказать','Написать','Оборудование','Дата','Компания','Недавно','Для','Приятно','Можно'}
    cities = [c for c in cities if c.split()[0] not in STOPCITY]
    rec['city_guess'] = cities[0] if cities else ''
    return rec

def work(u):
    u, src = fetch(u)
    return parse(u, src)

out = []
with ThreadPoolExecutor(max_workers=8) as ex:
    for n, rec in enumerate(ex.map(work, urls), 1):
        out.append(rec)
        if n % 100 == 0:
            print(f'{n}/{len(urls)}', file=sys.stderr)

json.dump(out, open('projects-index.json','w'), ensure_ascii=False, indent=1)
errs = sum(1 for r in out if r.get('error'))
print(f'done: {len(out)} records, {errs} errors', file=sys.stderr)
