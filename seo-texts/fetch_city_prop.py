# -*- coding: utf-8 -*-
import re, html as H, json, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36"
recs = json.load(open('projects-index.json'))
urls = [r['url'] for r in recs if not r.get('error')]

def work(u):
    try:
        r = subprocess.run(['curl','-sS','--max-time','40','-A',UA,u], capture_output=True, text=True, timeout=50)
        src = r.stdout
        i = src.find('class="properties"')
        if i < 0: return u, ''
        frag = re.sub(r'<script.*?</script>','',src[i:i+15000],flags=re.S)
        txt = H.unescape(re.sub(r'\|+','|',re.sub(r'<[^>]+>','|',frag)))
        m = re.search(r'\|Город\|?:?\|?\s*([^|]{2,60})', txt)
        if not m:
            m = re.search(r'Город\s*\|?\s*(г\.[^|]{2,60})', txt)
        val = m.group(1).strip() if m else ''
        val = re.sub(r'^г\.\s*', '', val).strip()
        return u, val
    except Exception:
        return u, ''

out = {}
with ThreadPoolExecutor(max_workers=8) as ex:
    for n, (u, val) in enumerate(ex.map(work, urls), 1):
        out[u] = val
        if n % 200 == 0: print(f'{n}/{len(urls)}', file=sys.stderr)

json.dump(out, open('city-prop.json','w'), ensure_ascii=False, indent=0)
print('with city prop:', sum(1 for v in out.values() if v), '/', len(out))
