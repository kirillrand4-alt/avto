# -*- coding: utf-8 -*-
import re, html as H, json, csv, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36"
BASE = "https://prokompressor.ru"

rows = list(csv.reader(open('elektricheskie-batch1.csv', encoding='utf-8-sig'), delimiter=';'))
header, rows = rows[0], rows[1:]
urls = [(r[0] if r[0].startswith('http') else BASE + r[0], r[1], r[2]) for r in rows if r and r[0].strip()]
print(f'{len(urls)} страниц', file=sys.stderr)

def parse(u, src):
    rec = {'url': u}
    if not src or len(src) < 5000:
        rec['error'] = 'empty'; return rec
    m = re.search(r'<title>(.*?)</title>', src); rec['title'] = H.unescape(m.group(1)) if m else ''
    m = re.search(r'name="description" content="(.*?)"', src); rec['description'] = H.unescape(m.group(1)) if m else ''
    m = re.search(r'<h1[^>]*>(.*?)</h1>', src, re.S)
    rec['h1'] = H.unescape(re.sub(r'<[^>]+>','',m.group(1)).strip()) if m else ''
    # фасетные диапазоны: minInputId -> ближайшее data-property_name
    for mm in re.finditer(r"'minInputId':'([^']+)'.*?'minPrice':'([\d.]+)','maxPrice':'([\d.]+)'(?:.*?'fltMinPrice':'([\d.]+)','fltMaxPrice':'([\d.]+)')?", src):
        pid = mm.group(1)
        j = src.rfind('data-property_name="', 0, src.find(pid))
        prop = src[j+20:src.find('"', j+20)] if j > 0 else pid
        lo, hi = mm.group(4) or '', mm.group(5) or ''
        if lo:
            key = 'price' if prop == 'Сайт' else prop
            rec.setdefault('ranges', {})[key] = [lo, hi]
    # товары первой страницы
    cards = re.findall(r'itemprop="url"[^>]*>\s*<span itemprop="name">([^<]+)</span>', src)
    rec['cards'] = [c.strip() for c in cards][:20]
    prices = re.findall(r'data-currency="RUB"[^>]*data-value="([\d.]+)"', src)
    rec['card_prices'] = sorted(set(float(p) for p in prices))[:25]
    pg = re.findall(r'PAGEN_1=(\d+)', src)
    rec['max_pagen'] = max(map(int, pg)) if pg else 1
    rec['min_products'] = (rec['max_pagen'] - 1) * len(rec['cards']) if rec['max_pagen'] > 1 else len(rec['cards'])
    # текущий нижний SEO-текст
    i = src.find('group_description_block bottom')
    if i > 0:
        frag = re.sub(r'<script.*?</script>','',src[i:i+9000],flags=re.S)
        txt = re.sub(r'\s+',' ', re.sub(r'<[^>]+>',' ',frag))
        txt = H.unescape(txt).strip()
        # обрезать по меню-хвосту
        for stop in ['Каталог Воздушные компрессоры','<li']:
            k = txt.find(stop)
            if k > 0: txt = txt[:k]
        rec['seo_text_now'] = txt[:400]
        rec['seo_text_len'] = len(txt)
    else:
        rec['seo_text_now'] = ''; rec['seo_text_len'] = 0
    return rec

def work(item):
    u, cluster, tag = item
    try:
        r = subprocess.run(['curl','-sS','--max-time','40','-A',UA,u], capture_output=True, text=True, timeout=50)
        rec = parse(u, r.stdout)
    except Exception as e:
        rec = {'url': u, 'error': str(e)[:100]}
    rec['cluster'] = cluster; rec['tag'] = tag
    return rec

out = []
with ThreadPoolExecutor(max_workers=6) as ex:
    for n, rec in enumerate(ex.map(work, urls), 1):
        out.append(rec)
        if n % 25 == 0: print(f'{n}/{len(urls)}', file=sys.stderr)

json.dump(out, open('elektro-pages.json','w'), ensure_ascii=False, indent=1)
errs = [r['url'] for r in out if r.get('error')]
print(f'готово: {len(out)}, ошибок {len(errs)}: {errs[:5]}', file=sys.stderr)
