# -*- coding: utf-8 -*-
"""Т2.6. Доказательства с сайта предприятия: разбор кэша страниц (зенка + конвейер) на слова машин.
Кэш: C:\\seostat\\drop\\pagecache\\<ИНН>.json.gz (страницы, собранные кубиком зенки) и C:\\seostat\\drop\\zenno\\gotovo\\<ИНН>_N.html.
Для каждой найденной машины пишем карточку: ссылка на КОНКРЕТНУЮ страницу сайта, цитата - окно ±180 знаков вокруг слова.
Заслоны: рекламные/каталожные страницы (продаём компрессоры) не считаются доказательством наличия у самого предприятия -
исключаются, если рядом слова продажи. argv: [бюджет] [TEST]."""
import os, sys, re, gzip, json, glob, time, html, sqlite3, collections
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
AK = r'C:\sender\_ops\ak'; DB = os.path.join(AK, 'AK-BAZA.sqlite')
KESH = os.environ.get('PAGECACHE_DIR', r'C:\seostat\drop\pagecache')
GOT = os.path.join(os.environ.get('ZENNO_OBMEN', r'C:\seostat\drop\zenno'), 'gotovo')
RAZ = os.path.join(os.environ.get('ZENNO_OBMEN', r'C:\seostat\drop\zenno'), 'razobrano')
F = os.path.join(AK, 'sayty-fakty.jsonl')
BUDGET = int(sys.argv[1]) if len(sys.argv) > 1 else 1400; TEST = 'TEST' in sys.argv
T0 = time.time(); TS = time.strftime('%Y-%m-%d %H:%M')
MASH = [('компрессорная станция', r'компрессорн\w+\s+(?:станци|установк|цех|отделени)'), ('генератор азота', r'(?:генератор|станци\w+|установк\w+)\s+азот|азотн\w+\s+(?:станци|генератор|установк)'),
        ('генератор кислорода', r'(?:генератор|станци\w+|установк\w+)\s+кислород|кислородн\w+\s+(?:станци|генератор|установк)'), ('ВРУ', r'воздухоразделительн\w+\s+установк|\bВРУ\b'),
        ('воздуходувка', r'воздуходувк|турбовоздуходувк|газодувк'), ('осушитель', r'осушител\w+\s+(?:сжатого\s+)?воздух'), ('ресивер', r'ресивер|воздухосборник'),
        ('компрессор', r'компрессор\w*'), ('сжатый воздух', r'сжат\w+\s+воздух|пневмосет|пневмолини|пневмотранспорт')]
MASH = [(v, re.compile(r, re.I)) for v, r in MASH]
PRODAZHA = re.compile(r'куп\w+|цена|прайс|заказ\w*\s+сейчас|в\s+корзин|доставка|каталог\s+товаров|наши\s+товары|продаж\w*\s+компрессор|дилер|поставщик\s+компрессор|интернет-магазин|руб\.?\s*/\s*шт|₽', re.I)
NASH = re.compile(r'наш\w*|у\s+нас|собственн\w*|предприяти\w*|цех\w*|установлен\w*|эксплуатир|производствен\w*|модерниз|введ\w+\s+в\s+эксплуатац|парк\s+оборудован|оснащ', re.I)
def okno(t, m, w=180):
    a = max(0, m.start() - w); b = min(len(t), m.end() + w)
    return re.sub(r'\s+', ' ', t[a:b]).strip()
def tekst(h):
    h = re.sub(r'(?is)<(script|style|nav|footer)[^>]*>.*?</\1>', ' ', h)
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', h)))
c = sqlite3.connect(DB, timeout=120)
nashi = {r[0] for r in c.execute("select inn from predpriyatiya where inn like '22%'")}
sayty = {r[0]: r[1] for r in c.execute("select inn, sayt from predpriyatiya where sayt is not null and sayt!=''")}
gotovo = set()
if os.path.exists(F):
    for l in open(F, encoding='utf-8'):
        try: gotovo.add(json.loads(l)['inn'])
        except Exception: pass
# --- источники страниц по ИНН
po_inn = collections.defaultdict(list)
for p in glob.glob(os.path.join(KESH, '*.json.gz')):
    inn = os.path.basename(p).split('.')[0]
    if inn in nashi: po_inn[inn].append(('kesh', p))
for d in (GOT, RAZ):
    if os.path.isdir(d):
        for p in glob.glob(os.path.join(d, '*.html')):
            m = re.match(r'(\d{10,12})', os.path.basename(p))
            if m and m.group(1) in nashi: po_inn[m.group(1)].append(('html', p))
ochered = [i for i in po_inn if i not in gotovo]
if TEST: ochered = ochered[:20]
print(f'ИНН края со страницами в кэше {len(po_inn)}, готово {len(gotovo)}, в очереди {len(ochered)}', flush=True)
f = open(F, 'a', encoding='utf-8'); n_f = n_i = 0; sch = collections.Counter()
for inn in ochered:
    if time.time() - T0 > BUDGET: break
    nayd = []
    for kind, p in po_inn[inn][:60]:
        try:
            if kind == 'kesh':
                d = json.loads(gzip.open(p, 'rt', encoding='utf-8', errors='replace').read())
                pg = d.get('pages') if isinstance(d, dict) else d
                stranicy = [((x.get('url') or ''), (x.get('html') or '')) for x in (pg or []) if isinstance(x, dict)]
            else:
                stranicy = [(sayty.get(inn, ''), open(p, encoding='utf-8', errors='replace').read())]
        except Exception as e:
            sch['сбой чтения'] += 1; continue
        for url, h in stranicy:
            if not h or len(h) < 500: continue
            t = tekst(h)
            for v, rx in MASH:
                for m in rx.finditer(t):
                    ok = okno(t, m)
                    if PRODAZHA.search(ok): sch['отсев продажа'] += 1; continue
                    if not NASH.search(ok): sch['отсев без признака нашего'] += 1; continue
                    nayd.append({'tip': v, 'url': url if isinstance(url, str) and url.startswith('http') else (('http://' + (sayty.get(inn) or '')) if sayty.get(inn) else ''), 'citata': ok})
                    break
            if len(nayd) >= 12: break
    f.write(json.dumps({'inn': inn, 'nayd': nayd[:12]}, ensure_ascii=False) + '\n'); f.flush(); gotovo.add(inn); n_i += 1
    for x in nayd[:12]:
        if not x['url']: continue
        cit = x['citata'][:500]
        c.execute('''insert or ignore into fakty(inn,predpriyatie,vid_fakta,tip,marka_model,sreda,data,srok_do,status_sroka,sila,istochnik,ssylka,citata,kto_sobral,ts,klyuch) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                  (inn, None, 'сайт предприятия', x['tip'], '', '', '', '', '', 2, re.sub(r'^https?://([^/]+).*', r'\1', x['url']), x['url'], cit, 'ak_sayty', TS, f'{inn}|{x["url"]}|{x["tip"]}||{cit[:80]}')); n_f += 1
    if n_i % 50 == 0: c.commit()
c.commit(); f.close()
print(f'разобрано ИНН за заход {n_i}, строк-кандидатов {n_f}, отсев: {dict(sch)}', flush=True)
print('факты сайтов:', c.execute("select count(*), count(distinct inn) from fakty where kto_sobral='ak_sayty'").fetchone(), flush=True)
c.close()
if not TEST and not [i for i in po_inn if i not in gotovo]: print('ГОТОВО')
