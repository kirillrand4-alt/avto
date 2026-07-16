# -*- coding: utf-8 -*-
"""Медиа-конвейер: классификация всех картинок -> полные карточки (кроме маркетинга/мусора).
Схемы/таблицы -> извлечение данных; фото -> карточка фотобанка с apply_to.
Резюмируемо: media-work/cards/<name>.json. Выход: kb/photo-bank.json, kb/media-data.json."""
import base64, glob, json, os, subprocess, sys
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_provider as gp
from kp_pipeline import drop_list, U, TOK

DIR = os.path.dirname(os.path.abspath(__file__))
MW = os.path.join(DIR, 'media-work'); RAW = os.path.join(MW, 'raw'); CARDS = os.path.join(MW, 'cards')
for d in (RAW, CARDS): os.makedirs(d, exist_ok=True)
IMG_EXT = ('jpg', 'jpeg', 'png')
SKIP_CLASSES = {'маркетинг', 'логотип_дизайн', 'прочее'}

# карты применимости: бренд -> дилерский домен; бренд -> слаги каталога
DEALER = {'berg':'berg-kompressor.ru','zif':'zif-kompressor.ru','dali':'dali-kompressor.ru',
 'cross air':'crossair-compressor.ru','crossair':'crossair-compressor.ru','abac':'abac-kompressor.ru',
 'ekomak':'ekomak-kompressor.com','remeza':'remeza-kompressor.ru','comaro':'comaro-kompressor.ru',
 'kraftmann':'kraftmann-kompressor.com','atlas copco':'ac-kompressor.ru','fini':'fini-compressor.com',
 'ironmac':'ironmac-compressor.com','comprag':'cmprg.ru','enger':'enger-air.ru'}
BRAND_SLUGS = {}
for f in glob.glob(os.path.join(DIR, 'gen', 'payload-*.json')):
    try: p = json.load(open(f))
    except: continue
    b = p.get('page_brand')
    if b: BRAND_SLUGS.setdefault(b.replace('_',' ').lower(), []).append(p['slug'])

def apply_to(brand, klass):
    b = (brand or '').lower().strip()
    out = {'dealer_site': DEALER.get(b), 'catalog_pages': (BRAND_SLUGS.get(b) or [])[:4]}
    out['usage'] = ('данные в kb' if klass in ('схема_чертёж','таблица_характеристик','шильдик_со_спеками')
                    else 'кейс-блок/иллюстрация статьи/фотобанк')
    return out

def b64(p):
    return base64.b64encode(open(p,'rb').read()).decode()

def call_batch(files, prompt_tail, effort='low'):
    content = []
    for n in files:
        p = os.path.join(RAW, n)
        ext = 'jpeg' if p.lower().endswith(('.jpg','.jpeg')) else 'png'
        content.append({'type':'text','text':f'--- {n}'})
        content.append({'type':'image','source':{'type':'base64','media_type':f'image/{ext}','data':b64(p)}})
    content.append({'type':'text','text':prompt_tail})
    client = gp.make_client()
    msg = gp.call(client, [{'role':'user','content':content}], model='claude-fable-5', effort=effort)
    return ''.join(b.text for b in msg.content if b.type=='text'), msg.usage

def main():
    names = [f['name'] for f in drop_list() if f['name'].startswith('kp')
             and f['name'].rsplit('.',1)[-1].lower() in IMG_EXT]
    todo_dl = [n for n in names if not os.path.exists(os.path.join(RAW,n))]
    print(f'картинок на дропе: {len(names)} | скачать: {len(todo_dl)}', flush=True)
    for i,n in enumerate(todo_dl,1):
        subprocess.run(['curl','-s','-H',f'X-Drop-Token: {TOK}',f'{U}/{n}','-o',os.path.join(RAW,n)],timeout=120)
        if i%50==0: print(f'  скачано {i}/{len(todo_dl)}', flush=True)
    # у некоторых сэмпл уже лежит в старой папке - переиспользуем
    for old in glob.glob(os.path.join(DIR,'kp-work','media-sample','kp*')):
        n=os.path.basename(old)
        if not n.endswith('.small.jpg') and not os.path.exists(os.path.join(RAW,n)):
            os.link(old, os.path.join(RAW,n))

    # ПРОХОД A: классификация некласифицированных
    unclass = [n for n in names if os.path.exists(os.path.join(RAW,n))
               and not os.path.exists(os.path.join(CARDS,n+'.json'))
               and os.path.getsize(os.path.join(RAW,n)) < 4_500_000]
    print(f'A) классифицировать: {len(unclass)}', flush=True)
    ti=to=0
    for bi in range(0,len(unclass),8):
        batch=unclass[bi:bi+8]
        try:
            out,u = call_batch(batch,
                'Для КАЖДОГО файла одна строка строго:\n<имя> | <класс: шильдик_со_спеками|таблица_характеристик|'
                'схема_чертёж|фото_товара|фото_с_объекта|маркетинг|сертификат|логотип_дизайн|прочее> | <бренд или -> | <кратко что видно>')
            ti+=u.input_tokens; to+=u.output_tokens
            for line in out.splitlines():
                p=[x.strip() for x in line.split('|')]
                if len(p)>=4 and p[0].startswith('kp'):
                    json.dump({'class':p[1],'brand':p[2] if p[2]!='-' else None,'note':p[3][:120]},
                              open(os.path.join(CARDS,p[0]+'.json'),'w'),ensure_ascii=False)
        except Exception as e:
            print(f'  классиф. пачка {bi//8+1} сбой: {e!r}'[:100], flush=True)
        if (bi//8)%10==9: print(f'  A: {bi+8}/{len(unclass)} | ~${ti*10/1e6+to*50/1e6:.2f}', flush=True)

    # ПРОХОД B: карточки для не-skip классов без card
    pend=[]
    for cf in glob.glob(os.path.join(CARDS,'*.json')):
        d=json.load(open(cf))
        if d.get('class') not in SKIP_CLASSES and 'card' not in d:
            pend.append(os.path.basename(cf)[:-5])
    data_cls={'схема_чертёж','таблица_характеристик','шильдик_со_спеками','сертификат'}
    print(f'B) карточек сделать: {len(pend)}', flush=True)
    for bi in range(0,len(pend),6):
        batch=[n for n in pend[bi:bi+6] if os.path.exists(os.path.join(RAW,n))]
        if not batch: continue
        try:
            out,u = call_batch(batch,
                'Для КАЖДОГО файла верни JSON-объект (все в одном JSON-массиве, без пояснений):\n'
                '{"file":"имя","brand":"...","models_visible":["..."],"description":"1-2 предложения",'
                '"alt_text":"для сайта","watermark":true/false,'
                '"extracted_data":{...}|null}\n'
                'extracted_data заполняй ТОЛЬКО для схем/таблиц/шильдиков: параметры, узлы, габариты, что читается.',
                effort='low')
            ti+=u.input_tokens; to+=u.output_tokens
            arr=gp.parse_json(type('M',(),{'content':[type('B',(),{'type':'text','text':out})()]})())
            if isinstance(arr,dict): arr=[arr]
            for card in arr:
                n=card.get('file','')
                cf=os.path.join(CARDS,n+'.json')
                if os.path.exists(cf):
                    d=json.load(open(cf))
                    card['apply_to']=apply_to(card.get('brand') or d.get('brand'), d.get('class'))
                    d['card']=card
                    json.dump(d,open(cf,'w'),ensure_ascii=False,indent=1)
        except Exception as e:
            print(f'  карточки пачка {bi//6+1} сбой: {e!r}'[:100], flush=True)
        if (bi//6)%10==9: print(f'  B: {bi+6}/{len(pend)} | ~${ti*10/1e6+to*50/1e6:.2f}', flush=True)

    # сборка выходов
    bank={}; mdata={}; stats=Counter()
    for cf in glob.glob(os.path.join(CARDS,'*.json')):
        n=os.path.basename(cf)[:-5]; d=json.load(open(cf))
        stats[d.get('class','?')]+=1
        c=d.get('card')
        if not c: continue
        if d['class'] in data_cls and c.get('extracted_data'): mdata[n]={**c,'class':d['class']}
        elif d['class'] not in SKIP_CLASSES: bank[n]={**c,'class':d['class']}
    os.makedirs(os.path.join(DIR,'kb'),exist_ok=True)
    json.dump(bank,open(os.path.join(DIR,'kb','photo-bank.json'),'w'),ensure_ascii=False,indent=1)
    json.dump(mdata,open(os.path.join(DIR,'kb','media-data.json'),'w'),ensure_ascii=False,indent=1)
    print(f'ИТОГ: классы {dict(stats)} | фотобанк {len(bank)} | данных {len(mdata)} | ~${ti*10/1e6+to*50/1e6:.2f}',flush=True)

if __name__=='__main__':
    main()
