import duckdb,json,csv,urllib.request,gzip,re,html,collections,concurrent.futures as cf,time
crawls=['CC-MAIN-2026-39','CC-MAIN-2026-34','CC-MAIN-2026-30','CC-MAIN-2026-25']
metas={c:[m for m in json.load(open(f'meta_{c}.json')) if m[1]] for c in crawls}
rows=[x for x in csv.DictReader(open('BAZA-PILOT-DOMENY.csv',encoding='utf-8-sig')) if x['status'].startswith('new')]
BANKS={'7707083893','7710140679','7728168971','7702070139','7725114488','7744000912','7750005725','7831000122','7744001497','7703000071','7704016014','7734202860','7740000076','7706092528','7744001151','2310050140'}
PRI=[('rekviz|requisit|rekvisit|kartochk',1),('politik|privacy|konfid|personal|pdn|152',2),('oferta|dogovor|agreement',3),('kontakt|contact',4),('about|o-kompanii|o_kompanii|company|o-nas|onas',5)]
def inn_ok(s):
    d=list(map(int,s))
    if len(d)==10: return (sum(a*b for a,b in zip([2,4,10,3,5,9,4,6,8],d[:9]))%11)%10==d[9]
    if len(d)==12:
        return (sum(a*b for a,b in zip([7,2,4,10,3,5,9,4,6,8],d[:10]))%11)%10==d[10] and (sum(a*b for a,b in zip([3,7,2,4,10,3,5,9,4,6,8],d[:11]))%11)%10==d[11]
    return False
def pages(con,d):
    a=d.encode('idna').decode() if not d.isascii() else d
    surt=','.join(reversed(a.split('.')));lo,hi=surt+')',surt+'-'
    got={}
    for c in crawls:
        fl=[m[0] for m in metas[c] if m[1]<=hi and m[2]>=lo]
        if not fl: continue
        for url,path,fn,off,ln,ft in con.execute("""select url,lower(url_path),warc_filename,warc_record_offset,warc_record_length,fetch_time from read_parquet(?)
            where url_surtkey>=? and url_surtkey<? and fetch_status=200 and (content_mime_detected like '%html%' or content_mime_detected is null)""",[fl,lo,hi]).fetchall():
            pr=6 if path in ('/','') else next((p for rx,p in PRI if re.search(rx,path)),None)
            if pr is None: continue
            key=url.split('://',1)[-1].rstrip('/')
            if key not in got or str(ft)>str(got[key][5]): got[key]=(pr,url,fn,off,ln,ft)
    return sorted(got.values(),key=lambda x:(x[0],len(x[1])))[:10]
def fetch(p):
    pr,url,fn,off,ln,ft=p
    for att in range(4):
        try:
            req=urllib.request.Request('https://data.commoncrawl.org/'+fn,headers={'Range':f'bytes={off}-{off+ln-1}'})
            raw=gzip.decompress(urllib.request.urlopen(req,timeout=60).read())
            body=raw.split(b'\r\n\r\n',2)[-1]
            t=body.decode('utf8','ignore')
            if re.search(r'charset=["\']?windows-1251',t[:5000],re.I): t=body.decode('cp1251','ignore')
            t=html.unescape(re.sub(r'<[^>]+>',' ',re.sub(r'(?is)<(script|style).*?</\1>',' ',t)));return re.sub(r'\s+',' ',t)
        except Exception: time.sleep(3*(att+1))
    return ''
fns=json.load(open('fnsmap.json'))
def work(x):
    con=duckdb.connect();con.execute("LOAD httpfs;")
    d=x['domain'];ps=pages(con,d)
    cand=collections.Counter();src={}
    unp=collections.Counter()
    for p in ps:
        t=fetch(p)
        for m in re.finditer(r'ИНН(?:\s*/\s*КПП)?\D{0,20}?(\d{10}|\d{12})(?!\d)',t):
            i=m.group(1)
            if inn_ok(i) and i not in BANKS:
                ctx=t[max(0,m.start()-120):m.start()].lower()
                w=0.3 if re.search(r'банк|разработ|студи|хостинг|beget|reg\.ru|получател',ctx) else 1
                cand[i]+=w*(2 if p[0]<=2 else 1); src.setdefault(i,(p[1],str(p[5])[:10]))
        for m in re.finditer(r'УНП\D{0,10}(\d{9})(?!\d)',t): unp[m.group(1)]+=1
    best=cand.most_common(1)[0][0] if cand else ''
    f=fns.get(best,['',None,'']) if best else ['',None,'']
    return {'domain':d,'segments':x['segments'],'regions':x['regions'],'title':x['title'][:120],'pages_cc':len(ps),
            'inn':best,'inn_kandidaty':';'.join(f'{k}:{v:g}' for k,v in cand.most_common(4)),'unp':unp.most_common(1)[0][0] if unp else '',
            'source_url':src.get(best,('',''))[0],'snapshot':src.get(best,('',''))[1],
            'fns_name':f[0],'income_2025':f[1] if f[1] is not None else '','okved_msp':f[2],'pilot_inn':x['inn']}
out=[]
with cf.ThreadPoolExecutor(6) as ex:
    for i,r in enumerate(ex.map(work,rows)):
        out.append(r)
        if i%50==0: print(i,flush=True)
w=csv.DictWriter(open('inn_novye_cc.csv','w',encoding='utf-8-sig'),fieldnames=list(out[0]));w.writeheader();w.writerows(out)
n=len(out);incc=sum(1 for r in out if r['pages_cc']);inn=sum(1 for r in out if r['inn']);un=sum(1 for r in out if r['unp'])
pil=sum(1 for r in out if r['pilot_inn']);both=sum(1 for r in out if r['inn'] or r['pilot_inn'])
agree=sum(1 for r in out if r['inn'] and r['pilot_inn'] and r['inn']==r['pilot_inn']);dis=sum(1 for r in out if r['inn'] and r['pilot_inn'] and r['inn']!=r['pilot_inn'])
infns=sum(1 for r in out if r['inn'] and (r['fns_name'] or r['okved_msp']))
print(f'доменов {n}; есть нужные страницы в CC {incc}; ИНН из CC {inn} ({inn/n:.0%}); УНП {un}; ИНН был в пилоте {pil}; ИНН хоть откуда {both} ({both/n:.0%}); совпало с пилотом {agree}, расходится {dis}; найден в данных ФНС {infns}')
print('done')
