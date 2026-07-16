import glob, json, re, os
from concurrent.futures import ThreadPoolExecutor, as_completed
from gen_provider import make_client, call
files = sorted(glob.glob('kb/manuf-raw/*.html'))
def clean(h):
    h = re.sub(r'<(script|style|nav|footer|svg)[^>]*>.*?</\1>', ' ', h, flags=re.S)
    h = re.sub(r'<[^>]+>', ' ', h); return re.sub(r'\s+', ' ', h).strip()
PROMPT = """Это текст с ОФИЦИАЛЬНОГО сайта производителя оборудования для сжатого воздуха «{slug}».
Извлеки факты О ПРОИЗВОДИТЕЛЕ (только то, что реально на странице; не выдумывай):
{text}
Верни ОДИН JSON: brand, country, founded, factories, product_types[], key_technologies[],
series_mentioned[], claims[] (маркетинговые заявления бренда), for_dealer_text[] (что можно
использовать в SEO как факт), confidence."""
client = make_client()
def worker(f):
    slug=os.path.basename(f)[:-5]; txt=clean(open(f,encoding='utf-8',errors='ignore').read())[:9000]
    if len(txt)<300: return {'brand':slug,'error':'мало текста'}
    msg=call(client,[{'role':'user','content':PROMPT.format(slug=slug,text=txt)}],'claude-fable-5')
    t=''.join(b.text for b in msg.content if b.type=='text'); m=re.search(r'\{.*\}',t,re.S)
    res=json.loads(m.group(0)); res['_slug']=slug; print(f'ок: {slug}',flush=True); return res
results=[]
with ThreadPoolExecutor(max_workers=8) as ex:
    futs={ex.submit(worker,f):f for f in files}
    for fu in as_completed(futs):
        try: results.append(fu.result())
        except Exception as e: print(f'FAIL {futs[fu]}: {repr(e)[:80]}',flush=True)
json.dump(results,open('kb/manuf-facts.json','w'),ensure_ascii=False,indent=1)
print('ИЗВЛЕЧЕНО с сайтов производителей:',len(results))
