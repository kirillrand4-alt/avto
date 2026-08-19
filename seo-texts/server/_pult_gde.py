# -*- coding: utf-8 -*-
r"""Где развёрнут пульт зенки и что сейчас отвечает диспетчер."""
import json
import os

найдено = []
for к in (r'C:\sender', r'C:\sender\sender', r'C:\sender\server', r'C:\seostat\drop'):
    if os.path.isdir(к):
        for и in os.listdir(к):
            if и.startswith('zenno'):
                найдено.append(os.path.join(к, и))
d = {'пульты': найдено}
p = r'C:\seostat\drop\zenno\dispetcher.json'
if os.path.exists(p):
    import time
    d['ответ_диспетчера'] = json.load(open(p, encoding='utf-8-sig'))
    d['возраст_сек'] = round(time.time() - os.path.getmtime(p))
print(json.dumps(d, ensure_ascii=False, indent=1)[:3000])
