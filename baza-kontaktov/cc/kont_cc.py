import duckdb,json,csv,urllib.request,gzip,re,html,collections,concurrent.futures as cf,time
exec(open('inn_cc.py').read().split("rows=")[0])  # crawls, metas, imports
src=open('inn_cc.py').read()
for name in ['BANKS','PRI','def inn_ok','def pages','def fetch']:
    pass
ns={}
code=src[src.index('BANKS='):src.index('fns=json.load')]
exec(code)
fns=json.load(open('fnsmap.json'))
rows=list(csv.DictReader(open('kontakty_vhod.csv',encoding='utf-8-sig')))
ROLE=r'(генеральн\w* директор\w*|исполнительн\w* директор\w*|коммерческ\w* директор\w*|технич\w* директор\w*|финансов\w* директор\w*|директор\w* по [а-яё]+(?: [а-яё]+)?|директор\w*|главн\w* (?:инженер|агроном|технолог|бухгалтер|механик|энергетик|зоотехник)\w*|заместител\w* директора(?: по [а-яё]+)?|начальник\w* [а-яё]+(?: [а-яё]+)?|заведующ\w* [а-яё]+|руководител\w* [а-яё]+(?: [а-яё]+)?|менеджер\w*(?: по [а-яё]+)?|технолог\w*|агроном\w*|инженер\w*|председател\w*|управляющ\w*|снабжен\w*|закуп\w*)'
FIO=r'([А-ЯЁ][а-яё]{1,20}(?:-[А-ЯЁ][а-яё]+)? [А-ЯЁ][а-яё]{1,15} [А-ЯЁ][а-яё]{2,20}(?:вич|вна|ична|чна|оглы|кызы))'
FIO2=r'([А-ЯЁ][а-яё]{1,20} [А-ЯЁ]\.\s?[А-ЯЁ]\.)'
PH=re.compile(r'(?<![\d])(?:\+7|8|\+375)[\s\-–(]*\d{2,5}[\s\-–)]*\d{1,3}[\s\-–]*\d{2}[\s\-–]*\d{2}(?![\d])')
EM=re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}')
def norm_ph(p):
    d=re.sub(r'\D','',p)
    if d.startswith('375') and len(d)==12: return '+'+d
    if len(d)==11 and d[0] in '78': return '+7'+d[1:]
    return None
def work(x):
    con=duckdb.connect();con.execute("LOAD httpfs;")
    d=x['domain']
    try: ps=pages(con,d)
    except Exception: ps=[]
    cand=collections.Counter();src={};phones=collections.Counter();emails=collections.Counter();people={}
    for p in ps:
        t=fetch(p)
        if not t: continue
        for m in re.finditer(r'ИНН(?:\s*/\s*КПП)?\D{0,20}?(\d{10}|\d{12})(?!\d)',t):
            i=m.group(1)
            if inn_ok(i) and i not in BANKS:
                ctx=t[max(0,m.start()-120):m.start()].lower()
                w=0.3 if re.search(r'банк|разработ|студи|хостинг|получател',ctx) else 1
                cand[i]+=w*(2 if p[0]<=2 else 1);src.setdefault(i,p[1])
        for m in PH.finditer(t):
            n=norm_ph(m.group(0))
            if n and not re.search(r'(р/с|к/с|счет|счёт|бик|окпо|огрн)\D{0,15}$',t[max(0,m.start()-30):m.start()].lower()): phones[n]+=1
        for e in EM.findall(t):
            e=e.lower().rstrip('.')
            if not re.search(r'\.(png|jpg|jpeg|gif|webp|svg)$|sentry|example|wixpress|domain\.',e): emails[e]+=1
        for rx,order in ((ROLE+r'[\s:–—\-,]{1,4}'+FIO,(1,0)),(FIO+r'[\s,–—\-]{1,4}'+ROLE,(0,1)),(ROLE+r'[\s:–—\-,]{1,4}'+FIO2,(1,0))):
            for m in re.finditer(rx,t):
                g=m.groups();fio=g[order[0]];role=g[order[1]]
                tail=t[m.end():m.end()+160]
                ph=[norm_ph(q) for q in PH.findall(tail)];ph=[q for q in ph if q][:2]
                em=EM.findall(tail)[:1]
                people.setdefault(fio,{'fio':fio,'role':role.strip(),'phones':ph,'email':em[0].lower() if em else '','url':p[1]})
    inn=cand.most_common(1)[0][0] if cand else (x.get('inn') or '').split('|')[0]
    f=fns.get(inn,['',None,'']) if inn else ['',None,'']
    mob=[q for q in phones if re.match(r'^\+79|^\+375(25|29|33|44)',q)]
    return {'domain':d,'src':x['src'],'status':x['status'],'segments':x['segments'],'title':x['title'][:150],'pages_cc':len(ps),
      'inn':inn,'inn_source':src.get(inn,''),'fns_name':f[0],'income_2025':f[1] if f[1] is not None else '','okved_msp':f[2],
      'phones':';'.join(q for q,_ in phones.most_common(8)),'mobile':';'.join(mob[:5]),'emails':';'.join(e for e,_ in emails.most_common(6)),
      'people':json.dumps(list(people.values())[:10],ensure_ascii=False)}
out=[]
with cf.ThreadPoolExecutor(8) as ex:
    for i,r in enumerate(ex.map(work,rows)):
        out.append(r)
        if i%100==0: print(i,len(rows),flush=True)
w=csv.DictWriter(open('kontakty_cc.csv','w',encoding='utf-8-sig'),fieldnames=list(out[0]));w.writeheader();w.writerows(out)
n=len(out);g=lambda f:sum(1 for r in out if f(r))
print(f"доменов {n}; есть страницы в CC {g(lambda r:r['pages_cc'])}; ИНН {g(lambda r:r['inn'])}; ИНН в ФНС {g(lambda r:r['fns_name'] or r['okved_msp'])}; телефон {g(lambda r:r['phones'])}; мобильный {g(lambda r:r['mobile'])}; e-mail {g(lambda r:r['emails'])}; ФИО+должность {g(lambda r:r['people']!='[]')}")
print('done')
