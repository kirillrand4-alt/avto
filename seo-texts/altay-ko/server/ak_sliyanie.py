# -*- coding: utf-8 -*-
"""Слияние готовых баз сервера в AK-BAZA: снимки парка машин, база центробежников, сигналы enrich,
тендеры Atlas Copco. Берём только ИНН края (22, длина 10/12). Дубли снимает уникальный ключ.
Ссылку тянем из fakt_ssylka (первоисточник в приоритете). argv: [POKAZAT]."""
import os, sys, re, sqlite3, collections
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
AK = r'C:\sender\_ops\ak'; DB = os.path.join(AK, 'AK-BAZA.sqlite')
POKAZAT = 'POKAZAT' in sys.argv
TS = __import__('time').strftime('%Y-%m-%d %H:%M')
DS = r'C:\seostat\drop\drop-storage'
PARKI = [('парк-снимок', os.path.join(DS, 'park-snimok.db')), ('парк-1с', os.path.join(DS, 'PARK-SNIMOK-1S.db')),
         ('парк-снапшот', os.path.join(DS, 'park_snapshot.db')), ('парк-панель', os.path.join(DS, 'park_panel.db')),
         ('парк-ранний', os.path.join(DS, 'park.db'))]
def ro(p): return sqlite3.connect(f'file:{p}?mode=ro', uri=True, timeout=90)

# Край - это ИНН на 22 ИЛИ адрес в Алтайском крае: у части заводов регистрация в другом регионе.
# «Республика Алтай» - чужой субъект, и её город Горно-Алтайск ловится наивным «Алтайск», поэтому
# ищем именно «Алтайский край» и почтовые индексы 656-659.
ADRES_KRAY = re.compile(r'Алтайский\s+кра[йя]|\b65[6-9]\d{3}\b', re.I)
NE_KRAY = re.compile(r'Республик\w*\s+Алтай|Горно-?Алтайск', re.I)
KRAY_INN = set()
def sobrat_adresa():
    isto = [r'C:\seostat\data\park_panel.db', os.path.join(DS, 'park-snimok.db'), os.path.join(DS, 'PARK-SNIMOK-1S.db'),
            os.path.join(DS, 'park_snapshot.db'), os.path.join(DS, 'atlas_copco.db'), r'C:\seostat\data\centrifugal.db']
    for p in isto:
        if not os.path.exists(p): continue
        try: s = ro(p)
        except Exception: continue
        for t, in s.execute("select name from sqlite_master where type='table'"):
            cols = [r[1] for r in s.execute('pragma table_info("%s")' % t)]
            ic = [x for x in cols if x.lower() == 'inn']
            rc = [x for x in cols if re.search(r'region|adres|address|subekt', x, re.I)]
            if not (ic and rc): continue
            for col in rc:
                try:
                    for i, a in s.execute('select %s, %s from "%s" where %s is not null' % (ic[0], col, t, col)):
                        i = (i or '').strip(); a = a or ''
                        if len(i) in (10, 12) and i.isdigit() and ADRES_KRAY.search(a) and not NE_KRAY.search(a): KRAY_INN.add(i)
                except Exception: pass
        s.close()
    try:
        d = ro(DB)
        for i, in d.execute("select inn from predpriyatiya where adres like '%Алтайский край%'"):
            if i: KRAY_INN.add(i.strip())
        d.close()
    except Exception: pass
sobrat_adresa()
print('ИНН края по адресу (сверх ИНН-22):', len({i for i in KRAY_INN if not i.startswith('22')}))
def kray(i):
    return isinstance(i, str) and len(i) in (10, 12) and (i.startswith('22') or i in KRAY_INN)
c = sqlite3.connect(DB, timeout=180)
POLYA = 'inn,predpriyatie,vid_fakta,tip,marka_model,sreda,data,srok_do,status_sroka,sila,istochnik,ssylka,citata,kto_sobral,ts,klyuch'
SQL = f'insert or ignore into fakty({POLYA}) values({",".join("?" * 16)})'
bylo = c.execute('select count(*) from fakty').fetchone()[0]
itogo = collections.Counter()

def polozhit(inn, nazv, vid, tip, marka, sreda, data, sila, istochnik, ssylka, citata, kto):
    citata = re.sub(r'\s+', ' ', (citata or '')).strip()[:600]
    if not inn or not citata: return
    klyuch = f'{inn}|{ssylka or ""}|{tip or ""}|{marka or ""}|{citata[:80]}'
    c.execute(SQL, (inn, nazv, vid, tip, marka, sreda, data, '', '', sila, istochnik, ssylka, citata, kto, TS, klyuch))
    itogo[kto] += 1

# --- снимки парка машин
for imya, p in PARKI:
    if not os.path.exists(p): continue
    s = ro(p)
    cols = [r[1] for r in s.execute('pragma table_info(fakt)')]
    ssyl = collections.defaultdict(list)
    try:
        sc = [r[1] for r in s.execute('pragma table_info(fakt_ssylka)')]
        pv = 'pervoistochnik' if 'pervoistochnik' in sc else None
        zapros = f'select fakt_id, url, istochnik{", " + pv if pv else ""} from fakt_ssylka'
        for r in s.execute(zapros):
            ssyl[r[0]].append((r[1], r[2], r[3] if pv else 0))
    except Exception: pass
    est = lambda n: n in cols
    for r in s.execute('select * from fakt'):
        d = dict(zip(cols, r))
        inn = (d.get('inn') or '').strip()
        if not kray(inn): continue
        vid = (d.get('vid_fakta') or '').strip()
        if vid == 'НЕТ': itogo[imya + ' (пропущено «НЕТ»)'] += 1; continue
        sp = sorted(ssyl.get(d.get('id'), []), key=lambda x: -(x[2] or 0))
        url = sp[0][0] if sp else ''
        ist = (sp[0][1] if sp else '') or re.sub(r'^https?://([^/]+).*', r'\1', url or '')
        marka = ' '.join(x for x in ((d.get('marka') or ''), (d.get('model') or '')) if x).strip()
        polozhit(inn, d.get('nazvanie'), 'парк: ' + (vid or 'машина'), d.get('tip'), marka, d.get('sreda'),
                 d.get('data_fakta'), d.get('sila') or 2, ist, url, d.get('chto_naydeno') or d.get('pochemu'), imya)
    s.close()

# --- база центробежников
p = r'C:\seostat\data\centrifugal.db'
if os.path.exists(p):
    s = ro(p)
    for r in s.execute('select inn,status,model,equipment_type,medium,event_date,evidence,quote,source_url,source from fact'):
        inn, st, mod, et, med, dt, ev, q, url, src = r
        if not kray((inn or '').strip()): continue
        polozhit(inn.strip(), None, 'центробежники: ' + (st or ''), et, mod or '', med, dt, 2, src or '', url or '',
                 ' | '.join(x for x in (q, ev) if x), 'центробежники')
    s.close()

# --- сигналы enrich
p = r'C:\sender\enrich.db'
if os.path.exists(p):
    s = ro(p)
    cols = [r[1] for r in s.execute('pragma table_info(signals)')]
    print('enrich.signals колонки:', cols)
    ic = 'inn' if 'inn' in cols else None
    if ic:
        for r in s.execute('select * from signals'):
            d = dict(zip(cols, r))
            inn = (d.get('inn') or '').strip()
            if not kray(inn): continue
            url = next((d[k] for k in cols if 'url' in k.lower() and d.get(k)), '')
            tx = ' | '.join(str(d[k]) for k in cols if d.get(k) and k.lower() in ('title', 'text', 'quote', 'citata', 'snippet', 'signal', 'kind', 'chto', 'opisanie'))
            polozhit(inn, None, 'сигнал enrich', '', '', '', str(d.get('date') or d.get('ts') or ''), 2,
                     re.sub(r'^https?://([^/]+).*', r'\1', url or ''), url or '', tx or str(d)[:300], 'enrich-сигналы')
    s.close()

# --- тендеры Atlas Copco
p = os.path.join(DS, 'atlas_copco.db')
if os.path.exists(p):
    s = ro(p)
    ploshch = collections.Counter()
    SHABLON = {'roseltorg': 'https://www.roseltorg.ru/procedure/{}', 'eis': 'https://zakupki.gov.ru/epz/order/notice/search/results.html?searchString={}',
               'zakupki': 'https://zakupki.gov.ru/epz/order/notice/search/results.html?searchString={}', 'b2b': 'https://www.b2b-center.ru/market/?action=view&id={}',
               'tenderpro': 'https://tender.pro/', 'tekторг': '', 'gpb': 'https://etpgpb.ru/procedures/{}/'}
    for pl, reg, zap, inn, kpp, org, fio, em, ph, tit, upd in s.execute('select platform,reg_number,query,inn,kpp,org,fio,email,phone,title,updated_at from tenders'):
        inn = (inn or '').strip()
        if not kray(inn): continue
        ploshch[pl] += 1
        nom = re.sub(r'^[a-z]+_', '', reg or '')
        sh = SHABLON.get((pl or '').lower(), '')
        url = sh.format(nom) if ('{}' in sh and nom) else (sh or '')
        polozhit(inn, org, 'закупка (Atlas Copco-прогон)', '', (zap or '').lower(), '', upd, 3 if url else 2,
                 pl or '', url, tit, 'atlas-тендеры')
    print('площадки Atlas-прогона по краю:', dict(ploshch))
    s.close()

if POKAZAT: c.rollback()
else: c.commit()
stalo = c.execute('select count(*) from fakty').fetchone()[0]
print('--- влито по источникам (попыток):')
for k, n in itogo.most_common(): print(f'   {k}: {n}')
print(f'карточек было {bylo}, стало {stalo}, прибавка {stalo - bylo}')
print('предприятий с фактами:', c.execute('select count(distinct inn) from fakty').fetchone()[0])
c.close()
