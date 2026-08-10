# -*- coding: utf-8 -*-
# МЕРКА, У КОТОРОЙ КОНТРОЛЬ НАКОНЕЦ РАБОТАЕТ. Две прежние попытки провалились:
# 1) «цифры ИНН есть в тексте» — страница печатает сам ЗАПРОС, и выдуманный ИНН «находился»;
# 2) «есть ссылка на карточку организации» — на странице выдуманного ИНН ЕИС всё равно
#    показывает какую-то организацию (у меня вышла тестовая, ИНН 4444444486).
# Работает третье: ИНН из факта обязан стоять СРАЗУ ПОСЛЕ слова «ИНН» на странице.
import collections, io, json, os, random, re, subprocess, sys, threading
SCR='/tmp/claude-0/-home-user-avto/66783df1-79e2-513f-8bfb-9c49a1f69007/scratchpad'
RUN='server/run_on_server.py'
st=[]
for f in ('park_ingest_3b.jsonl',):
    for s in io.open(os.path.join(SCR,f),encoding='utf-8'):
        o=json.loads(s)
        if o.get('ssylka_inn'): st.append(o)
random.seed(321); obr=random.sample(st,20)
KONTROL={'inn':'9999999999','ssylka_inn':'https://zakupki.gov.ru/epz/organization/search/results.html?searchString=9999999999'}
zamok=threading.Lock(); och=list(obr)+[KONTROL]; sch=collections.Counter(); kontrol=[None]
INN_POSLE=re.compile(r'ИНН\s*([0-9]{10,12})')
def rab():
    while True:
        with zamok:
            if not och: return
            o=och.pop()
        args={'url':o['ssylka_inn'],'screenshot':False,'return_html':False,'wait_ms':15000,
              'proxy':False,'ignore_https_errors':True,
              'eval_js':{'return':'document.body ? document.body.innerText : ""','after_ms':1400}}
        try:
            p=subprocess.run([sys.executable,RUN,'browser_probe',json.dumps(args,ensure_ascii=False)],capture_output=True,timeout=400)
            s=p.stdout.decode('utf-8','replace'); d=json.loads(s[s.find('{'):]).get('data') or {}
            t=re.sub(r'\s+',' ',str(d.get('eval_js_value') or ''))
        except Exception: t=''
        est = bool(t) and (o['inn'] in INN_POSLE.findall(t))
        with zamok:
            if o is KONTROL: kontrol[0]=est
            elif not t: sch['не прочёл прибор']+=1
            else: sch['ИНН напечатан на странице' if est else 'ИНН на странице ДРУГОЙ']+=1
n=[threading.Thread(target=rab) for _ in range(4)]
for x in n: x.start()
for x in n: x.join()
print('\n########## ПРОВЕРКА МОИХ ССЫЛОК НА ИНН, браузером, жребий 321')
for k,v in sch.most_common(): print('   %-40s %3d'%(k,v))
print('   ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ (ИНН 9999999999): %s'
      % ('на странице другой ИНН — мерка умеет говорить нет' if not kontrol[0] else 'СЧЁЛ ДОКАЗАННЫМ — МЕРКА ВРЁТ'))
