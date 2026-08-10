# -*- coding: utf-8 -*-
"""Проба: как ОКВЭД записан на карточке чеко. Регулярку строим по живому тексту."""
import json, os, re, sys, urllib.request
import requests
DROP=os.environ.get('DROP_URL','https://parsercompressor.online/drop').rstrip('/')
TOKEN=os.environ.get('DROP_TOKEN','')
def dg(i):
    return urllib.request.urlopen(urllib.request.Request(f'{DROP}/{i}',headers={'X-Drop-Token':TOKEN}),timeout=120).read()
px=[('socks5://'+s.strip()) for s in dg('dolphin-proxies.txt').decode('utf-8','replace').splitlines() if s.strip() and '@' in s]
UA={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'}
p=px[0]; pr={'http':p,'https':p}
r=requests.get('https://checko.ru/search?query=6626005553',headers=UA,timeout=40,allow_redirects=True,proxies=pr)
k=str(r.url).split('?')[0].rstrip('/')
t=re.sub(r'\s+',' ',re.sub(r'<[^>]+>',' ',r.text))
for slovo in ('ОКВЭД','Основной вид','Виды деятельности','Выручка'):
    i=t.find(slovo)
    print(json.dumps({'слово':slovo,'позиция':i,'кусок':t[max(0,i-60):i+320] if i>=0 else ''},ensure_ascii=False))
