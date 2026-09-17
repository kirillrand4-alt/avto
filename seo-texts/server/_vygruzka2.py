# -*- coding: utf-8 -*-
"""Выгрузка очищенной базы: события + агрегат по уникальным компаниям."""
import csv, io, json, os, re, sqlite3, time, collections

DIR = r'C:\sender\server'
метки = {}
with io.open(os.path.join(DIR, 'otbor_90kvt.jsonl'), encoding='utf-8', errors='replace') as f:
    for s in f:
        try: з = json.loads(s)
        except Exception: continue
        if not з.get('ошибка'):
            метки[(str(з.get('inn')), з.get('url'))] = (bool(з.get('a')), bool(з.get('b')))

ПРОЕКТ=('планиру','намерен','построит','создаст','инвестиц','соглашен','резидент','проект','анонс','вложит')
СТРОЙКА=('строит','строительств','возвод','монтаж','котлован')
ПУСК=('запуск','запустил','открыл','ввёл','ввод в эксплуатац','пусконаладк')
РАСШИР=('расширен','модерниз','техперевооруж','реконструкц','увеличил мощност','вторая очередь')
def стадия(t,w):
    x=((t or '')+' '+(w or '')).lower()
    if any(k in x for k in ПУСК): return '3 пуск'
    if any(k in x for k in СТРОЙКА): return '2 стройка'
    if any(k in x for k in РАСШИР): return '4 расширение'
    if any(k in x for k in ПРОЕКТ): return '1 проект'
    return '0 не определена'

c = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True, timeout=60)
строки = c.execute(
    "select s.inn, coalesce(cmp.name,''), coalesce(cmp.division,''), coalesce(cmp.region,''), "
    "s.source, s.event_type, s.what, coalesce(s.sum,''), s.hotness, coalesce(s.inn_conf,''), "
    "s.source_url, substr(s.updated_at,1,16), coalesce(cmp.site,''), coalesce(cmp.best_email,'') "
    'from signals s left join companies cmp on cmp.inn=s.inn order by s.hotness desc, s.rowid desc'
).fetchall()
c.close()

def линия(inn,url):
    a,b = метки.get((str(inn),url),(None,None))
    return 'обе линии' if a and b else 'компрессор 90+' if a else 'Meyer' if b else 'не размечено'

имя1='sobytiya-%s.csv'%time.strftime('%d%m'); п1=os.path.join(DIR,имя1)
with io.open(п1,'w',encoding='utf-8-sig',newline='') as f:
    w=csv.writer(f,delimiter=';')
    w.writerow(['ИНН','компания','линия','направление','регион','источник','тип события',
                'что происходит','сумма','важность','стадия','уверенность в ИНН','ссылка',
                'узнали','сайт','почта'])
    for (inn,name,div,reg,src,et,what,sm,hot,conf,url,upd,site,mail) in строки:
        w.writerow([inn,name,линия(inn,url),div,reg,src,et,
                    re.sub(r'\s+',' ',what or '')[:600],sm,hot,стадия(et,what),conf,url,upd,site,mail])
    f.flush(); os.fsync(f.fileno())

# --- агрегат по компаниям
по_инн=collections.OrderedDict()
for (inn,name,div,reg,src,et,what,sm,hot,conf,url,upd,site,mail) in строки:
    k=str(inn)
    з=по_инн.setdefault(k,{'ИНН':k,'компания':name,'направление':div,'регион':reg,
                           'сайт':site,'почта':mail,'событий':0,'макс важность':0,
                           'линии':set(),'стадии':set(),'суммы':[],'последнее':'',
                           'лучший повод':'','ссылка':''})
    з['событий']+=1
    з['линии'].add(линия(inn,url)); з['стадии'].add(стадия(et,what))
    if sm: з['суммы'].append(sm)
    if int(hot or 0)>з['макс важность']:
        з['макс важность']=int(hot or 0)
        з['лучший повод']=re.sub(r'\s+',' ',what or '')[:300]; з['ссылка']=url
    if upd>з['последнее']: з['последнее']=upd

имя2='kompanii-%s.csv'%time.strftime('%d%m'); п2=os.path.join(DIR,имя2)
with io.open(п2,'w',encoding='utf-8-sig',newline='') as f:
    w=csv.writer(f,delimiter=';')
    w.writerow(['ИНН','компания','линия','направление','регион','событий','макс важность',
                'стадии','суммы','лучший повод','ссылка','последнее событие','сайт','почта'])
    for з in sorted(по_инн.values(), key=lambda x:(-x['макс важность'],-x['событий'])):
        w.writerow([з['ИНН'],з['компания'],' / '.join(sorted(з['линии'])),з['направление'],
                    з['регион'],з['событий'],з['макс важность'],' / '.join(sorted(з['стадии'])),
                    ' | '.join(з['суммы'][:3]),з['лучший повод'],з['ссылка'],з['последнее'],
                    з['сайт'],з['почта']])
    f.flush(); os.fsync(f.fileno())
try:
    import shutil
    for и,п in ((имя1,п1),(имя2,п2)):
        shutil.copyfile(п, os.path.join(r'C:\seostat\drop\drop-storage', и))
except Exception: pass
print('===ИТОГ===')
print(json.dumps({'событий':len(строки),'компаний':len(по_инн),
                  'файлы':[имя1,имя2]}, ensure_ascii=False))
