import duckdb,json,urllib.request,gzip,re,html,time,os,concurrent.futures as cf,threading
rows=duckdb.connect().execute("select d,url,warc_filename,warc_record_offset,warc_record_length from 'roots_cand.parquet'").fetchall()
done=set()
if os.path.exists('scored.jsonl'):
    for l in open('scored.jsonl'):
        try: done.add(json.loads(l)['d'])
        except: pass
rows=[r for r in rows if r[0] not in done]
S={ # (маркеры, стоп-слова)
'exp':(r'экспорт\w*|\bвэд\b|\bfob\b|\bcif\b|трейдинг\w*|зернов\w* терминал|перевалк\w*|сдиз|фитосанитар\w*|\bexport\w*|grain|oilseed|pulses',r'таможенн\w* брокер'),
'seed':(r'семен(?:а|ами|ах|ной|ного|ном)\b|семеновод\w*|гибрид\w*|оригинатор\w*|суперэлит\w*|\bэлит\w*|репродукц\w*|семенн\w* завод|протравлив\w*|калибровк\w* семян|посевн\w* материал\w*|селекц\w*|\bрс1\b|\bрс2\b',r'семена для дачи|интернет-магазин семян|сорт кофе'),
'food':(r'(?:пищев\w*|молочн\w*|мясн\w*|хлебо\w*|кондитерск\w*|масложиров\w*|консервн\w*|мукомольн\w*|сахарн\w*) (?:производств\w*|завод\w*|комбинат\w*|предприят\w*|фабрик\w*|продукци\w*)|\bхассп\b|\bhaccp\b|iso 22000|тр тс 021|собственн\w* производств\w*|линия розлива|цех\w* по производству',r'\bкафе\b|ресторан\w*|доставка еды|суши|пицц\w*'),
'elev':(r'элеватор\w*|\bхпп\b|\bкхп\b|зернохранилищ\w*|приемк\w* зерна|приёмк\w* зерна|сушк\w* зерна|зерносушилк\w*|подработк\w* зерна|доработк\w* зерна|очистк\w* зерна|хранени\w* зерна|единовременного хранения|комбикорм\w*',r'элеваторн\w* узел|отоплени\w*|теплоснабжени\w*|гидроэлеватор\w*|\bлифт\w*|\bитп\b'),
'nuts':(r'\bорех\w*|фундук\w*|грецк\w* орех\w*|миндал\w*|кешью|фисташк\w*|кедров\w* орех\w*|ядро ореха|колк\w* орех\w*|ореховодств\w*',r'пиломатериал\w*|мебел\w*|шпон\w*|орехово-зуев\w*'),
'berr':(r'\bягод\w*|клубник\w*|земляник\w*|малин(?:а|ы|у|ой|ник\w*)\b|смородин\w*|голубик\w*|клюкв\w*|брусник\w*|облепих\w*|жимолост\w*|шоков\w* заморозк\w*|\biqf\b|ягодн\w* питомник\w*|конфитюр\w*',r'малиновк\w*'),
}
NEG=r'в корзину|корзина товаров|рецепт\w*|\bблог\b|отзывы покупателей|доставка по москве за|купить онлайн|новости региона|информационное агентство|\bсми\b'
PROD=r'производ\w*|завод\w*|выращива\w*|собственн\w*|хозяйств\w*|предприяти\w*|питомник\w*|переработ\w*|комбинат\w*|агрохолдинг\w*|фабрик\w*'
SC={k:(re.compile(a,re.I),re.compile(b,re.I)) for k,(a,b) in S.items()}
NEGR=re.compile(NEG,re.I);PRODR=re.compile(PROD,re.I)
INN=re.compile(r'ИНН\D{0,20}?(\d{10}|\d{12})(?!\d)');UNP=re.compile(r'УНП\D{0,10}(\d{9})(?!\d)')
def inn_ok(s):
    d=list(map(int,s))
    if len(d)==10: return (sum(a*b for a,b in zip([2,4,10,3,5,9,4,6,8],d[:9]))%11)%10==d[9]
    return (sum(a*b for a,b in zip([7,2,4,10,3,5,9,4,6,8],d[:10]))%11)%10==d[10] and (sum(a*b for a,b in zip([3,7,2,4,10,3,5,9,4,6,8],d[:11]))%11)%10==d[11]
lock=threading.Lock();out=open('scored.jsonl','a')
def work(r):
    d,url,fn,off,ln=r
    for att in range(5):
        try:
            req=urllib.request.Request('https://data.commoncrawl.org/'+fn,headers={'Range':f'bytes={off}-{off+ln-1}','User-Agent':'baza-kontaktov-research/1.0'})
            raw=gzip.decompress(urllib.request.urlopen(req,timeout=60).read());break
        except urllib.error.HTTPError as e:
            if e.code in (503,429): time.sleep(5*(att+1));continue
            return {'d':d,'err':e.code}
        except Exception as e: time.sleep(3*(att+1))
    else: return {'d':d,'err':'fail'}
    body=raw.split(b'\r\n\r\n',2)[-1]
    t=body.decode('utf8','ignore')
    if re.search(r'charset=["\']?(windows-1251|cp1251)',t[:5000],re.I): t=body.decode('cp1251','ignore')
    ti=re.search(r'(?is)<title[^>]*>(.*?)</title>',t);ti=html.unescape(re.sub(r'\s+',' ',ti.group(1))).strip()[:200] if ti else ''
    h1=' '.join(re.findall(r'(?is)<h1[^>]*>(.*?)</h1>',t))[:500]
    txt=html.unescape(re.sub(r'<[^>]+>',' ',re.sub(r'(?is)<(script|style|noscript)[^>]*>.*?</\1>',' ',t)));txt=re.sub(r'\s+',' ',txt)
    head=(ti+' '+html.unescape(re.sub(r'<[^>]+>',' ',h1))).lower();low=txt.lower()
    sc={}
    for k,(a,b) in SC.items():
        hits=a.findall(low);s=min(len(hits),10)+2*len(a.findall(head))+min(len(set(h.lower() for h in hits)),5)
        s-=3*len(b.findall(low))
        sc[k]=s
    inns=[i for i in INN.findall(txt) if inn_ok(i)]
    res={'d':d,'url':url,'title':ti,'len':len(txt),'sc':sc,'neg':len(NEGR.findall(low)),'prod':len(PRODR.findall(low)),
         'inn':inns[0] if inns else '','unp':(UNP.findall(txt) or [''])[0],'snip':txt[:400],
         'tel79':len(re.findall(r'(?:\+7|8)[\s(-]*9\d\d',txt)),'by375':len(re.findall(r'\+375',txt))}
    return res
n=0;t0=time.time()
with cf.ThreadPoolExecutor(32) as ex:
    for res in ex.map(work,rows):
        with lock: out.write(json.dumps(res,ensure_ascii=False)+'\n');out.flush()
        n+=1
        if n%2000==0: print(n,len(rows),f'{n/(time.time()-t0):.1f}/s',flush=True)
print('done')
