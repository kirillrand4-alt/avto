# -*- coding: utf-8 -*-
import re, html as H, json, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36"
BASE = "https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/dizelnye/"
SLUGS = ['airbox','ariacom','atmos','aztec','bezhetsk','comprag','cross-air','dalgakiran','dali','das',
'enger','et-compressors','kraftmachine','magnus','master-blast-','minskiy-motornyy-zavod','ozen','remeza','zega','zif']

def min_diesel_price(slug):
    u = BASE + slug + '/?sort=CATALOG_PRICE_44&order=asc'
    try:
        r = subprocess.run(['curl','-sS','--max-time','40','-A',UA,u], capture_output=True, text=True, timeout=50)
        src = r.stdout
    except Exception:
        return slug, None, None
    # пары (позиция имени, имя)
    cards = [(m.start(), H.unescape(m.group(1))) for m in re.finditer(r'itemprop="url"[^>]*>\s*<span itemprop="name">([^<]+)</span>', src)]
    prices = [(m.start(), float(m.group(1))) for m in re.finditer(r'data-currency="RUB"[^>]*data-value="([\d.]+)"', src)]
    for pos, name in cards:
        if 'бензин' in name.lower(): continue
        nxt = [p for pp, p in prices if pp > pos]
        if nxt:
            return slug, nxt[0], name.strip()
    return slug, None, None

out = {}
with ThreadPoolExecutor(max_workers=6) as ex:
    for slug, price, name in ex.map(min_diesel_price, SLUGS):
        out[slug] = {'min_diesel_price': price, 'model': name}
        print(f'{slug:<24} {price} | {name}', file=sys.stderr)
json.dump(out, open('diz-min-prices.json','w'), ensure_ascii=False, indent=1)
