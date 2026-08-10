# -*- coding: utf-8 -*-
"""Проверяю формат телефона в живой карточке: было «3462410034», должно быть «+7 (3462) 41-00-34»."""
import json, os, re, urllib.parse, urllib.request, http.cookiejar
B='http://127.0.0.1:8012/obzvon'
PW=''
if os.path.exists(r'C:\sender\centro-user3.txt'):
    t=open(r'C:\sender\centro-user3.txt',encoding='utf-8',errors='replace').read()
    m=re.search(r'(?:пароль|password)\s*[:=]\s*(\S+)', t, re.I); PW=m.group(1) if m else t.strip().split()[-1]
cj=http.cookiejar.CookieJar(); op=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
op.open(B+'/centro/login', timeout=30)
op.open(urllib.request.Request(B+'/centro/login', data=urllib.parse.urlencode(
    {'username':'user3','password':PW}).encode()), timeout=40)
with op.open(B+'/centro/park/8602060555', timeout=90) as r: s=r.read().decode('utf-8','replace')
o={'знаков': len(s),
   'голых 10 цифр подряд (плохо)': len(re.findall(r'>\s*34624\d{5}\s*<', s)),
   'в формате +7 (3462)': s.count('+7 (3462)'),
   'tel: с +7': len(re.findall(r'href="tel:\+7\d{10}"', s)),
   'метка «прямой рабочий»': s.count('прямой рабочий'),
   'метка «личный мобильный»': s.count('личный мобильный'),
   'старая метка «личный» отдельно': len(re.findall(r'>личный<', s))}
i=s.find('+7 (3462)')
o['кусок'] = re.sub(r'\s+',' ', s[max(0,i-160):i+80]) if i>0 else ''
print(json.dumps(o, ensure_ascii=False, indent=1))
