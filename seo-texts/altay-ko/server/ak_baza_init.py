# -*- coding: utf-8 -*-
"""Фаза 0. Каркас AK-BAZA.sqlite на сервере: срез Алтайского края из всех местных баз и парка машин.
Запуск на сервере (panel_py). Идемпотентен: таблицы создаются IF NOT EXISTS, вставки INSERT OR IGNORE/UPSERT.
Вывод пишет в C:\\sender\\_ops\\ak\\init.out (хвост stdout режется)."""
import os, sys, re, json, csv, sqlite3, time, urllib.request, io
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
csv.field_size_limit(10**8)
AK = r'C:\sender\_ops\ak'; os.makedirs(AK, exist_ok=True)
DB = os.path.join(AK, 'AK-BAZA.sqlite')
OUT = []
def p(*a): OUT.append(' '.join(str(x) for x in a)); print(OUT[-1], flush=True)
DROP_URL = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/')
DROP_TOKEN = os.environ.get('DROP_TOKEN', '')

def drop_down(name, dest):
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return dest
    req = urllib.request.Request(f'{DROP_URL}/{name}', headers={'X-Drop-Token': DROP_TOKEN})
    with urllib.request.urlopen(req, timeout=600) as r, open(dest, 'wb') as f:
        while True:
            b = r.read(1 << 20)
            if not b: break
            f.write(b)
    return dest

RESP_ALTAY = re.compile(r'респ\w*\.?\s*алтай|алтай\s*респ|горно-алтайск', re.I)
KRAY = re.compile(r'алтайск\w*\s+кра', re.I)
def region_ok(inn, adres):
    """Край = ИНН на 22 или адрес с «Алтайский край»; Республика Алтай (04, «Респ Алтай») - нет."""
    inn = inn or ''; a = adres or ''
    if RESP_ALTAY.search(a) and not KRAY.search(a):
        return False
    if inn.startswith('22'):
        return True
    return bool(KRAY.search(a))

def chislo(s):
    """'5,7 млрд руб.' / '322,4 млн руб.' / '4100000000.0' / '641 человек +312' -> число или None."""
    if s is None: return None
    if isinstance(s, (int, float)): return float(s)
    t = str(s).replace('\xa0', ' ').strip().lower()
    if not t: return None
    m = re.search(r'(-?\d[\d\s]*(?:[.,]\d+)?)', t)
    if not m: return None
    v = float(m.group(1).replace(' ', '').replace(',', '.'))
    if 'млрд' in t: v *= 1e9
    elif 'млн' in t: v *= 1e6
    elif 'тыс' in t: v *= 1e3
    return v

c = sqlite3.connect(DB, timeout=60)
c.executescript('''
create table if not exists predpriyatiya(
  inn text primary key, ogrn text, nazvanie text, nazvanie_polnoe text, status_egrul text, gorod text, adres text,
  okved_osn text, okved_vse text, sayt text, activity text, ssch integer, rukovoditel text,
  istochniki_zapisi text, sayt_fakty_json text, klass text, uverennost integer, tehprocess text, tip_mashin text,
  ts text);
create table if not exists finansy(
  inn text, istochnik text, fin_god text, vyruchka_rub real, pribyl_rub real, nalogi_rub real, ssch integer, ts text,
  primary key(inn, istochnik, fin_god));
create table if not exists fakty(
  id integer primary key autoincrement, inn text, predpriyatie text, vid_fakta text, tip text, marka_model text,
  sreda text, data text, srok_do text, status_sroka text, sila integer, istochnik text, ssylka text, citata text,
  kto_sobral text, ts text, klyuch text unique);
create table if not exists progony(trek text, klyuch text, sostoyanie text, chisla_json text, ts text, primary key(trek, klyuch));
create table if not exists kontroli(trek text, vhod text, ozhidalos text, polucheno text, ok integer, ts text);
create index if not exists fakty_inn on fakty(inn);
''')
TS = time.strftime('%Y-%m-%d %H:%M')

def upsert_pred(inn, **kw):
    inn = ''.join(ch for ch in str(inn or '') if ch.isdigit())
    if len(inn) not in (10, 12): return False
    row = c.execute('select * from predpriyatiya where inn=?', (inn,)).fetchone()
    cols = [d[1] for d in c.execute('pragma table_info(predpriyatiya)')]
    if row is None:
        d = dict.fromkeys(cols); d['inn'] = inn; d['ts'] = TS
    else:
        d = dict(zip(cols, row))
    src = kw.pop('istochnik', '')
    for k, v in kw.items():
        if v in (None, '', 'None'): continue
        if k not in cols: continue
        if d.get(k) in (None, '') or (k == 'okved_vse' and len(str(v)) > len(str(d.get(k) or ''))):
            d[k] = v
    s = set((d.get('istochniki_zapisi') or '').split('|')) - {''}
    if src: s.add(src)
    d['istochniki_zapisi'] = '|'.join(sorted(s))
    c.execute(f'insert or replace into predpriyatiya({",".join(cols)}) values({",".join("?"*len(cols))})', [d[k] for k in cols])
    return True

def add_fin(inn, istochnik, god, vyr, prib, nal=None, ssch=None):
    inn = ''.join(ch for ch in str(inn or '') if ch.isdigit())
    if not inn or (vyr is None and prib is None and nal is None and ssch is None): return
    c.execute('insert or replace into finansy values(?,?,?,?,?,?,?,?)', (inn, istochnik, str(god or ''), vyr, prib, nal, int(ssch) if ssch else None, TS))

def add_fakt(**k):
    inn = ''.join(ch for ch in str(k.get('inn') or '') if ch.isdigit())
    if not inn or not k.get('ssylka'): return False
    kl = f'{inn}|{k.get("ssylka")}|{k.get("tip","")}|{k.get("marka_model","")}|{(k.get("citata") or "")[:80]}'
    try:
        c.execute('''insert or ignore into fakty(inn,predpriyatie,vid_fakta,tip,marka_model,sreda,data,srok_do,status_sroka,sila,istochnik,ssylka,citata,kto_sobral,ts,klyuch)
                     values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                  (inn, k.get('predpriyatie'), k.get('vid_fakta'), k.get('tip'), k.get('marka_model'), k.get('sreda'), k.get('data'),
                   k.get('srok_do'), k.get('status_sroka'), k.get('sila'), k.get('istochnik'), k.get('ssylka'), k.get('citata'),
                   k.get('kto_sobral'), TS, kl))
        return c.total_changes
    except Exception as e:
        return False

# ---------- 1. master-base (солянка) ----------
n = 0
m = sqlite3.connect(r'file:C:\sender\master-base.sqlite?mode=ro', uri=True); m.row_factory = sqlite3.Row
for r in m.execute("select * from master where inn like '22%' or address like '%Алтайск%'"):
    if not region_ok(r['inn'], r['address']): continue
    upsert_pred(r['inn'], nazvanie=r['name_obzvon'] or r['name'], nazvanie_polnoe=r['name'], status_egrul=r['egrul_status'], gorod=r['region'],
                adres=r['address'], okved_osn=r['okved'], okved_vse=r['okved_all'], sayt=r['site'], activity=r['activity'], rukovoditel=r['director'], istochnik='master')
    v = chislo(r['revenue_rub'])
    if v: add_fin(r['inn'], 'master', '', v, None)
    n += 1
m.close(); p('master: строк края', n)
# ---------- 2. obzvon-index ----------
n = 0
o = sqlite3.connect(r'file:C:\sender\obzvon-index.db?mode=ro', uri=True); o.row_factory = sqlite3.Row
for r in o.execute("select * from obzvon where inn like '22%' or address like '%Алтайск%' or region like '%Алтайск%'"):
    if not region_ok(r['inn'], (r['address'] or '') + ' ' + (r['region'] or '')): continue
    upsert_pred(r['inn'], ogrn=r['ogrn'], nazvanie=r['name_short'], nazvanie_polnoe=r['name_full'], status_egrul=r['status'], adres=r['address'],
                okved_osn=r['okved_main'], okved_vse=r['okved_all_codes'], sayt=(r['sites'] or '').split(';')[0].split('|')[0].strip(), rukovoditel=r['director'], istochnik='obzvon')
    add_fin(r['inn'], 'obzvon', r['god_otch'], chislo(r['revenue']) or chislo(r['revenue_rub']), chislo(r['profit']), None, chislo(r['ssch']))
    n += 1
o.close(); p('obzvon: строк края', n)
# ---------- 3. enrich.db ----------
e = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True); e.row_factory = sqlite3.Row
n = 0
for r in e.execute("select * from companies where inn like '22%' or region like '%Алтайск%' or address like '%Алтайск%'"):
    if not region_ok(r['inn'], (r['address'] or '') + ' ' + (r['region'] or '')): continue
    upsert_pred(r['inn'], ogrn=r['ogrn'], nazvanie=r['short_name'] or r['name'], nazvanie_polnoe=r['name'], status_egrul=r['status_egrul'], adres=r['address'],
                okved_osn=r['okved'], okved_vse=r['okved_all'], sayt=r['site'] or r['site_checko'], activity=r['activity'], rukovoditel=r['director'], istochnik='enrich.companies')
    if r['revenue_rub']: add_fin(r['inn'], 'enrich.companies', r['revenue_year'], chislo(r['revenue_rub']), None)
    n += 1
p('enrich.companies: строк края', n)
n = 0
for r in e.execute("select * from requisites where inn like '22%' or address like '%Алтайск%'"):
    if not region_ok(r['inn'], r['address']): continue
    upsert_pred(r['inn'], ogrn=r['ogrn'], nazvanie=r['name_short'], nazvanie_polnoe=r['name_full'], status_egrul=r['status'], adres=r['address'],
                okved_osn=r['okved_main'] or r['okved_main_checko'], okved_vse=r['okved_all_checko'] or r['okved_all'], sayt=r['site_checko'],
                rukovoditel=r['director'], ssch=int(r['ssch']) if r['ssch'] else None, istochnik='enrich.requisites')
    if r['revenue_rub'] or r['profit_rub']: add_fin(r['inn'], 'checko(requisites)', r['fin_god'], chislo(r['revenue_rub']), chislo(r['profit_rub']), None, r['ssch'])
    n += 1
p('enrich.requisites: строк края', n)
n = 0
inns = {r[0] for r in c.execute('select inn from predpriyatiya')}
for r in e.execute("select inn, facts_json, site from site_facts"):
    if r['inn'] in inns:
        c.execute('update predpriyatiya set sayt_fakty_json=?, sayt=coalesce(nullif(sayt,\'\'),?) where inn=?', (r['facts_json'], r['site'], r['inn'])); n += 1
p('site_facts по краю привязано', n)
e.close()
# ---------- 4. checko_finansy.jsonl ----------
n = 0
for line in open(r'C:\sender\server\checko_finansy.jsonl', encoding='utf-8', errors='replace'):
    try: d = json.loads(line)
    except Exception: continue
    if str(d.get('inn', '')).startswith('22'):
        add_fin(d['inn'], 'checko(finansy)', d.get('fin_god'), chislo(d.get('revenue_rub')), chislo(d.get('profit_rub')), None, d.get('ssch'))
        upsert_pred(d['inn'], ogrn=d.get('ogrn'), istochnik='checko_finansy'); n += 1
p('checko_finansy: строк края', n)
# ---------- 5. парк машин с дропа ----------
def rd(name):
    path = drop_down(name, os.path.join(AK, name))
    with open(path, encoding='utf-8-sig', errors='replace', newline='') as f:
        rdr = csv.DictReader(f, delimiter=';')
        for row in rdr: yield row
n = nf = 0
for r in rd('PARK-VYDACHA-FAKTY-2S.csv'):
    if not (r.get('inn') or '').startswith('22'): continue
    n += 1
    upsert_pred(r['inn'], nazvanie=r.get('predpriyatie'), istochnik='park-fakty-2s')
    if add_fakt(inn=r['inn'], predpriyatie=r.get('predpriyatie'), vid_fakta='ЭПБ', tip=r.get('tip'), marka_model=r.get('marka_model'), sreda=r.get('sreda'),
                data=r.get('data'), srok_do=r.get('srok_do'), status_sroka=r.get('status_sroka'), sila=r.get('sila'), istochnik=r.get('istochnik') or 'monitor-pb.ru',
                ssylka=r.get('ssylka'), citata=r.get('citata'), kto_sobral='2с парк'): nf += 1
p('PARK-VYDACHA-FAKTY-2S: строк края', n, 'фактов записано', nf)
n = nf = 0
for r in rd('PARK-VYDACHA-OPO-2S.csv'):
    if not (r.get('inn') or '').startswith('22'): continue
    n += 1
    if add_fakt(inn=r['inn'], vid_fakta='ОПО', tip=r.get('naimenovanie_obekta'), marka_model=r.get('reg_nomer'), sreda=r.get('klass_opasnosti'), sila=3,
                istochnik='monitor-pb.ru', ssylka=r.get('ssylka'), citata=r.get('citata'), kto_sobral='2с парк'): nf += 1
p('PARK-VYDACHA-OPO-2S: строк края', n, 'фактов', nf)
n = 0
for r in rd('PARK-VYDACHA-PREDPRIYATIYA-2S.csv'):
    if not (r.get('inn') or '').startswith('22'): continue
    n += 1
    upsert_pred(r['inn'], nazvanie=r.get('predpriyatie'), nazvanie_polnoe=r.get('nazvanie_egrul'), adres=r.get('adres'), sayt=r.get('sayt'), rukovoditel=r.get('rukovoditel'),
                status_egrul=r.get('status_egrul'), okved_osn=r.get('okved_osnovnoy'), okved_vse=(r.get('okved_kody') or '').replace(' ', '|'), istochnik='park-predpr-2s')
    if r.get('vyruchka'): add_fin(r['inn'], 'checko(park-2s)', r.get('vyruchka_god'), chislo(r.get('vyruchka')), None)
p('PARK-VYDACHA-PREDPRIYATIYA-2S: строк края', n)
n = nf = 0
for r in rd('PARK-BAZA-EDINAYA-3S.csv'):
    if not (r.get('inn') or '').startswith('22'): continue
    n += 1
    upsert_pred(r['inn'], nazvanie=r.get('predpriyatie'), istochnik='park-baza-3s')
    for ss in (r.get('mashina_ssylka') or '').split(' | '):
        ss = ss.strip()
        if ss and add_fakt(inn=r['inn'], predpriyatie=r.get('predpriyatie'), vid_fakta='закупка/парк-3с', tip=r.get('mashina'), sila=3,
                           istochnik=re.sub(r'^https?://([^/]+).*', r'\1', ss), ssylka=ss, citata=(r.get('citata') or '')[:400], kto_sobral='3с база'): nf += 1
p('PARK-BAZA-EDINAYA-3S: строк края', n, 'фактов машины', nf)
# ЕИС карточки 1-й сессии (park_obshchie_inn.jsonl и др.)
for name in ['park_obshchie_inn.jsonl', 'park_gaz_inn.jsonl', 'park_brendy_inn.jsonl']:
    n = nf = 0
    fp = os.path.join(r'C:\sender', name)
    if not os.path.exists(fp): continue
    for line in open(fp, encoding='utf-8', errors='replace'):
        try: d = json.loads(line)
        except Exception: continue
        inns_ = [d.get('inn')] + list(d.get('inn_vse') or [])
        for inn in inns_:
            if inn and str(inn).startswith('22'):
                n += 1
                upsert_pred(inn, nazvanie=d.get('zakazchik_iz_lenty'), istochnik='eis-1s')
                if add_fakt(inn=inn, predpriyatie=d.get('zakazchik_iz_lenty'), vid_fakta='закупка ЕИС' if d.get('os') != 'расход газа' else 'расход газа ЕИС', tip=d.get('zapros'), sila=4,
                            istochnik='zakupki.gov.ru', ssylka=d.get('url_kartochki'), citata=(d.get('predmet') or '')[:400], kto_sobral='1с ЕИС'): nf += 1
    p(name, 'строк края', n, 'фактов', nf)
c.commit()
# ---------- свод ----------
p('== ИТОГ predpriyatiya:', c.execute('select count(*) from predpriyatiya').fetchone()[0],
  '| с ОКВЭД:', c.execute("select count(*) from predpriyatiya where okved_osn is not null and okved_osn!=''").fetchone()[0],
  '| с адресом:', c.execute("select count(*) from predpriyatiya where adres is not null and adres!=''").fetchone()[0],
  '| с сайтом:', c.execute("select count(*) from predpriyatiya where sayt is not null and sayt!=''").fetchone()[0],
  '| с сайт-фактами:', c.execute("select count(*) from predpriyatiya where sayt_fakty_json is not null").fetchone()[0])
p('== finansy: строк', c.execute('select count(*) from finansy').fetchone()[0], '| ИНН с выручкой:', c.execute('select count(distinct inn) from finansy where vyruchka_rub>0').fetchone()[0],
  '| ИНН с прибылью:', c.execute('select count(distinct inn) from finansy where pribyl_rub is not null').fetchone()[0], '| по источникам:', c.execute('select istochnik, count(*) from finansy group by 1').fetchall())
p('== fakty:', c.execute('select count(*) from fakty').fetchone()[0], '| ИНН с фактом:', c.execute('select count(distinct inn) from fakty').fetchone()[0],
  '| по видам:', c.execute('select vid_fakta, count(*) from fakty group by 1').fetchall())
p('== статусы:', c.execute('select status_egrul, count(*) from predpriyatiya group by 1 order by 2 desc limit 8').fetchall())
p('== ИНН не на 22 (по адресу):', c.execute("select count(*) from predpriyatiya where inn not like '22%'").fetchone()[0])
c.close()
open(os.path.join(AK, 'init.out'), 'w', encoding='utf-8').write('\n'.join(OUT))
print('записано', sum(len(x) + 1 for x in OUT))
