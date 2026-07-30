# -*- coding: utf-8 -*-
"""Приёмы 2 и 3: пробуем пути вакансий и «о компании/структура» на сайтах предприятий.
Кодировку определяем сами (ловушка В10). Пишем сырой HTML — потом разбираем."""
import json,os,re,subprocess,sys,collections
from concurrent.futures import ThreadPoolExecutor
D='/tmp/claude-0/-home-user-avto/520847fd-7699-5483-869b-cf6d49851f67/scratchpad/pr3'
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'
VAK=['/vakansii/','/vakansii','/vacancy/','/vacancies/','/career/','/careers/','/jobs/','/rabota/',
     '/o-kompanii/vakansii/','/company/vacancy/','/hr/']
ABOUT=['/about/','/about-us/','/o-kompanii/','/o-nas/','/our-team/','/komanda/','/struktura/',
       '/company/structure/','/about/structure/','/rukovodstvo/']
def get(url,timeout=25,maxb=600000):
    p=subprocess.run(['curl','-sSL','-A',UA,'--compressed','-k','--max-time',str(timeout),
                      '-w','\n@@CODE:%{http_code} URL:%{url_effective} SIZE:%{size_download}',
                      '-o','-',url],capture_output=True)
    raw=p.stdout
    i=raw.rfind(b'\n@@CODE:')
    meta=raw[i+1:].decode('latin-1','replace') if i>=0 else ''
    body=raw[:i] if i>=0 else raw
    m=re.search(r'@@CODE:(\d+) URL:(\S+) SIZE:(\d+)',meta)
    code,eff,size=(m.group(1),m.group(2),int(m.group(3))) if m else ('000','',0)
    enc=None
    mm=re.search(rb'(?i)charset=["\']?([\w\-]+)',body[:4000])
    if mm:
        e=mm.group(1).decode('latin-1').lower()
        if e not in ('iso-8859-1','latin1','us-ascii','ascii'): enc=e
    if not enc:
        try: body[:200000].decode('utf-8'); enc='utf-8'
        except Exception: enc='cp1251'
    try: txt=body.decode(enc,'replace')
    except Exception: txt=body.decode('utf-8','replace')
    return {'code':code,'eff':eff,'size':size,'enc':enc,'html':txt[:maxb]}

def zadanie(t):
    dom,path=t
    r=get(f'https://{dom}{path}')
    if r['code']=='000':
        r=get(f'http://{dom}{path}')
    return dom,path,r

def main():
    doms=json.load(open(D+'/domeny-filtr.json'))
    tasks=[(d,p) for d in doms for p in (VAK+ABOUT)]
    print('доменов',len(doms),'заданий',len(tasks),file=sys.stderr)
    os.makedirs(D+'/pages2',exist_ok=True)
    res=[]
    with ThreadPoolExecutor(max_workers=16) as ex:
        for i,(dom,path,r) in enumerate(ex.map(zadanie,tasks)):
            key=re.sub(r'[^a-z0-9]+','_',(dom+path).lower())
            ok = r['code'] in ('200',) and r['size']>1500
            if ok:
                open(f'{D}/pages2/{key}.html','w',encoding='utf-8').write(r['html'])
            res.append({'domain':dom,'path':path,'code':r['code'],'size':r['size'],
                        'eff':r['eff'],'enc':r['enc'],'file':key+'.html' if ok else ''})
            if i%100==0: print(i,file=sys.stderr)
    json.dump(res,open(D+'/probe2.json','w'),ensure_ascii=False,indent=1)
    c=collections.Counter((x['path'],x['code']=='200' and x['size']>1500) for x in res)
    for p in VAK+ABOUT:
        print(p, 'открылось:',c[(p,True)],'из',len(doms))
main()
