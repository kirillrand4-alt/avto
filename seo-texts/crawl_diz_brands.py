# -*- coding: utf-8 -*-
import re, html as H, json, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36"
BASE = "https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/dizelnye/"
SLUGS = ['airbox','ariacom','atlas-copco','atmos','aztec','bezhetsk','comprag','cross-air','dalgakiran',
'dali','das','enger','et-compressors','kraftmachine','magnus','master-blast-','minskiy-motornyy-zavod',
'ozen','remeza','zega','zif']

def parse(u, src):
    rec = {'url': u}
    if not src or len(src) < 5000:
        rec['error'] = 'empty'; return rec
    m = re.search(r'<title>(.*?)</title>', src); rec['title'] = H.unescape(m.group(1)) if m else ''
    m = re.search(r'name="description" content="(.*?)"', src); rec['description'] = H.unescape(m.group(1)) if m else ''
    m = re.search(r'<h1[^>]*>(.*?)</h1>', src, re.S)
    rec['h1'] = H.unescape(re.sub(r'<[^>]+>','',m.group(1)).strip()) if m else ''
    for mm in re.finditer(r"'minInputId':'([^']+)'.*?'minPrice':'([\d.]+)','maxPrice':'([\d.]+)'(?:.*?'fltMinPrice':'([\d.]+)','fltMaxPrice':'([\d.]+)')?", src):
        pid = mm.group(1)
        j = src.rfind('data-property_name="', 0, src.find(pid))
        prop = src[j+20:src.find('"', j+20)] if j > 0 else pid
        if mm.group(4):
            key = 'price' if prop == 'Сайт' else prop
            rec.setdefault('ranges', {})[key] = [mm.group(4), mm.group(5)]
    cards = re.findall(r'itemprop="url"[^>]*>\s*<span itemprop="name">([^<]+)</span>', src)
    rec['cards'] = [c.strip() for c in cards][:20]
    pg = re.findall(r'PAGEN_1=(\d+)', src)
    rec['max_pagen'] = max(map(int, pg)) if pg else 1
    i = src.find('group_description_block bottom')
    if i > 0:
        frag = re.sub(r'<script.*?</script>','',src[i:i+9000],flags=re.S)
        txt = H.unescape(re.sub(r'\s+',' ', re.sub(r'<[^>]+>',' ',frag))).strip()
        for stop in ['Каталог Воздушные компрессоры']:
            k = txt.find(stop)
            if k > 0: txt = txt[:k]
        rec['seo_now'] = txt[:200]; rec['seo_len'] = len(txt)
    return rec

def work(slug):
    u = BASE + slug + '/'
    try:
        r = subprocess.run(['curl','-sS','--max-time','40','-A',UA,u], capture_output=True, text=True, timeout=50)
        rec = parse(u, r.stdout)
    except Exception as e:
        rec = {'url': u, 'error': str(e)[:80]}
    rec['slug'] = slug
    return rec

out = []
with ThreadPoolExecutor(max_workers=6) as ex:
    out = list(ex.map(work, SLUGS))
json.dump(out, open('diz-brands-pages.json','w'), ensure_ascii=False, indent=1)
for r in out:
    rng = r.get('ranges', {}).get('price', ['',''])
    print(f"{r['slug']:<24} h1={r.get('h1','?')[:45]:<47} стр={r.get('max_pagen','?'):<3} цена {rng[0]}–{rng[1]} | seo_len={r.get('seo_len',0)}", file=sys.stderr)
