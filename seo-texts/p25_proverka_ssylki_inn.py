# -*- coding: utf-8 -*-
"""Проверяю СВОЮ ЖЕ новую ссылку на ИНН: правда ли на ней видны ИНН и название.
Дописала её 9 141 факту по одной пробе на ЮГК — этого мало, меряю выборкой.
ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ: выдуманный ИНН обязан не дать организации."""
import collections, io, json, os, random, re, ssl, urllib.request
OPS=r'C:\sender\_ops'
UA=('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
ctx=ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
net=urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx), urllib.request.ProxyHandler({}))
TEG=re.compile(r'<(script|style)[^>]*>.*?</\1>|<[^>]+>', re.S|re.I)
def tekst(u):
    try:
        return re.sub(r'\s+',' ',TEG.sub(' ', net.open(urllib.request.Request(u,headers={'User-Agent':UA}),timeout=40).read(300000).decode('utf-8','replace')))
    except Exception as e: return ''
stroki=[]
for f in ('park_ingest_3.jsonl','park_ingest_3b.jsonl','park_ingest_3c.jsonl','park_ingest_3d.jsonl'):
    p=os.path.join(OPS,f)
    if not os.path.exists(p): continue
    for s in io.open(p,encoding='utf-8'):
        try: o=json.loads(s)
        except Exception: continue
        if o.get('ssylka_inn'): stroki.append(o)
random.seed(int(os.environ.get('P25_ZHREBIY','321')))
obr=random.sample(stroki,min(20,len(stroki)))
sch=collections.Counter()
for o in obr:
    t=tekst(o['ssylka_inn'])
    if not t: sch['страница не открылась']+=1; continue
    # КОНТРОЛЬ ПРОБИТ ПЕРВЫМ ЗАХОДОМ, И ПОДЕЛОМ: страница ЕИС печатает сам ЗАПРОС в поле
    # поиска, поэтому «цифры ИНН есть в тексте» выполняется даже для выдуманного ИНН.
    # Мерка обязана отличать напечатанные ДАННЫЕ от эха запроса: требую, чтобы на странице
    # была НАЙДЕННАЯ организация (ссылка на её карточку) и не было слов «не найдено».
    est = (o['inn'] in re.sub(r'\D','',t)) and ('не найдено' not in t.lower()) \
        and bool(re.search(r'/epz/organization/view', t, re.I))
    sch['ИНН виден и организация найдена' if est else 'организации на странице нет']+=1
kt=tekst('https://zakupki.gov.ru/epz/organization/search/results.html?searchString=9999999999')
kontrol = bool(kt) and ('9999999999' in re.sub(r'\D','',kt)) \
    and ('не найдено' not in kt.lower()) and bool(re.search(r'/epz/organization/view', kt, re.I))
print('\n\n########## ЧИСЛА')
print('  фактов с новой ссылкой на ИНН: %d' % len(stroki))
print('  проверено выборкой: %d' % len(obr))
for k,v in sch.most_common(): print('     %-40s %3d'%(k,v))
print('  ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ (ИНН 9999999999): %s'
      % ('организации нет — мерка умеет говорить нет' if not kontrol else 'НАШЁЛ ОРГАНИЗАЦИЮ — МЕРКА ВРЁТ'))
print('ИТОГ '+json.dumps({'проверено':len(obr),'ИНН виден':sch['ИНН виден и организация найдена'],'контроль':bool(kontrol)},ensure_ascii=False))
