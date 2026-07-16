# -*- coding: utf-8 -*-
"""Мини-краул фото проектов (og:image), только для проектов, реально используемых в payload.
Ноль LLM. Выход: projects-photos.json {rel_project_url: photo_url}."""
import json, os, re, requests
from concurrent.futures import ThreadPoolExecutor, as_completed
DIR=os.path.dirname(os.path.abspath(__file__))
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36'
urls=[l.strip() for l in open(os.path.join(DIR,'used-projects.txt')) if l.strip()]
def one(rel):
    full='https://prokompressor.ru'+rel
    try:
        h=requests.get(full,headers={'User-Agent':UA},timeout=30).text
        og=re.search(r'og:image\"\s+content=\"(https://prokompressor\.ru/upload/[^\"]+)\"',h)
        if og and not og.group(1).endswith('.svg'):
            return rel, og.group(1).replace('https://prokompressor.ru','')
        # запасной: первое medialibrary фото
        m=re.search(r'<img[^>]+src=\"(/upload/(?:medialibrary|iblock)/[^\"]+\.(?:jpg|jpeg|png))\"',h,re.I)
        if m: return rel, m.group(1)
    except Exception as e:
        return rel, None
    return rel, None
res={}
with ThreadPoolExecutor(max_workers=8) as ex:
    for f in as_completed([ex.submit(one,u) for u in urls]):
        rel,ph=f.result()
        if ph: res[rel]=ph
json.dump(res, open(os.path.join(DIR,'projects-photos.json'),'w'), ensure_ascii=False, indent=1)
print(f'фото найдено: {len(res)}/{len(urls)}')
