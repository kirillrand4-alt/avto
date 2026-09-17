# -*- coding: utf-8 -*-
"""Выгрузка очищенной базы с меткой линии (компрессор / Meyer)."""
import csv, io, json, os, re, sqlite3, time

DIR = r'C:\sender\server'
метки = {}
with io.open(os.path.join(DIR, 'otbor_90kvt.jsonl'), encoding='utf-8', errors='replace') as f:
    for s in f:
        try: з = json.loads(s)
        except Exception: continue
        if з.get('ошибка'): continue
        метки[(str(з.get('inn')), з.get('url'))] = (bool(з.get('a')), bool(з.get('b')))

ПРОЕКТ=('планиру','намерен','построит','создаст','инвестиц','соглашен','резидент','проект','анонс','вложит')
СТРОЙКА=('строит','строительств','возвод','монтаж','котлован')
ПУСК=('запуск','запустил','открыл','ввёл','ввод в эксплуатац','пусконаладк','завершил строительств')
РАСШИР=('расширен','модерниз','техперевооруж','реконструкц','увеличил мощност','вторая очередь')
def стадия(t, w):
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
    "s.source_url, substr(s.updated_at,1,16), coalesce(s.ts,''), coalesce(cmp.site,''), "
    "coalesce(cmp.best_email,'') from signals s left join companies cmp on cmp.inn=s.inn "
    'order by s.hotness desc, s.rowid desc').fetchall()
c.close()

имя = 'signaly-chistye-%s.csv' % time.strftime('%d%m')
путь = os.path.join(DIR, имя)
with io.open(путь, 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f, delimiter=';')
    w.writerow(['ИНН','компания','линия','направление в базе','регион','источник','тип события',
                'что происходит','сумма','важность','стадия','уверенность в ИНН','ссылка',
                'узнали','дата события','сайт','почта'])
    сч = {'компрессор':0,'Meyer':0,'обе':0,'не размечено':0}
    for р in строки:
        (inn,name,div,reg,src,et,what,sm,hot,conf,url,upd,ts,site,mail) = р
        a,b = метки.get((str(inn), url), (None,None))
        линия = ('обе линии' if a and b else 'компрессор 90+' if a else 'Meyer' if b
                 else 'не размечено')
        сч['обе' if a and b else 'компрессор' if a else 'Meyer' if b else 'не размечено'] += 1
        w.writerow([inn,name,линия,div,reg,src,et,re.sub(r'\s+',' ',what or '')[:600],
                    sm,hot,стадия(et,what),conf,url,upd,ts,site,mail])
    f.flush(); os.fsync(f.fileno())
try:
    import shutil
    shutil.copyfile(путь, os.path.join(r'C:\seostat\drop\drop-storage', имя))
except Exception: pass
print('===ИТОГ===')
print(json.dumps({'строк': len(строки), 'файл': имя, 'по_линиям': сч}, ensure_ascii=False))
