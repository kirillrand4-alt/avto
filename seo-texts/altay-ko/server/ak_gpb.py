# -*- coding: utf-8 -*-
"""Т2.4. ЭТП ГПБ (etpgpb.ru) по словам через API, фильтр по lot_regions «Алтайский край».
API: /api/v2/procedures/?page=N&per=200&sort=by_relevance&procedure[stage][0]=all&search=<слово> (потолок 400 страниц, поиск нечёткий).
ИНН заказчика: страница /customers/<slug>/ (кэш gpb-customers.jsonl). Резюм по (слово, страница) в gpb-lenta.jsonl. argv: [бюджет] [TEST]."""
import os, sys, re, json, time, html, sqlite3, requests
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
requests.packages.urllib3.disable_warnings()
AK = r'C:\sender\_ops\ak'; DB = os.path.join(AK, 'AK-BAZA.sqlite')
F_L = os.path.join(AK, 'gpb-lenta.jsonl'); F_C = os.path.join(AK, 'gpb-customers.jsonl')
BUDGET = int(sys.argv[1]) if len(sys.argv) > 1 else 1400; TEST = 'TEST' in sys.argv
T0 = time.time(); TS = time.strftime('%Y-%m-%d %H:%M')
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36', 'Accept': 'application/json, text/html'}
S = requests.Session(); S.headers.update(UA)
GRUPPY = {'закупка машины': ['компрессор', 'компрессорная станция', 'воздуходувка', 'осушитель сжатого воздуха', 'генератор азота', 'генератор кислорода', 'ресивер воздушный', 'винтовой компрессор', 'воздухоразделительная'],
          'закупка ТО': ['обслуживание компрессора', 'ремонт компрессора', 'обслуживание компрессорного оборудования'],
          'закупка запчастей': ['запчасти компрессор', 'масло компрессорное', 'фильтр компрессора', 'ремкомплект компрессора']}
if TEST: GRUPPY = {'закупка машины': ['компрессор']}
REG = re.compile(r'Алтайск\w*\s+кра', re.I)
AVTO = re.compile(r'автомоб|\bзил\b|камаз|трактор|шасси|тормозн|двигател|кондиционер|холодильн', re.I)
VIDY = [('генератор кислорода', r'кислородн'), ('генератор азота', r'азотн'), ('ВРУ', r'воздухоразделительн'), ('воздуходувка', r'воздуходув'), ('осушитель', r'осушител'), ('ресивер', r'ресивер|воздухосборник'),
        ('компрессорная станция', r'компрессорн\w+\s+станц'), ('запчасти', r'запасн|запчаст|масло|фильтр|ремкомплект'), ('компрессор', r'компрессор')]
VIDY = [(v, re.compile(r, re.I)) for v, r in VIDY]
def vid(s):
    for v, rx in VIDY:
        if rx.search(s or ''): return v
    return ''
gotovo = set(); lenta = {}
if os.path.exists(F_L):
    for l in open(F_L, encoding='utf-8'):
        try: d = json.loads(l)
        except Exception: continue
        gotovo.add(d['klyuch'])
        for z in d.get('zapisi', []): lenta.setdefault(z['id'], z)
f = open(F_L, 'a', encoding='utf-8'); n_new = 0
for gr, slova in GRUPPY.items():
    for slovo in slova:
        for pg in range(1, 401):
            kl = f'{slovo}|{pg}'
            if kl in gotovo: continue
            if time.time() - T0 > BUDGET: break
            try:
                r = S.get('https://etpgpb.ru/api/v2/procedures/', params={'page': pg, 'per': 200, 'sort': 'by_relevance', 'procedure[stage][0]': 'all', 'search': slovo}, timeout=90, verify=False)
                j = r.json(); items = j.get('data') or []
            except Exception as e:
                print('gpb err', slovo, pg, repr(e)[:80]); time.sleep(5); continue
            zapisi = []
            for it in items:
                a = it.get('attributes') or {}
                if not any(REG.search(x or '') for x in (a.get('lot_regions') or [])): continue
                zapisi.append({'id': it.get('id'), 'nomer': a.get('registry_number'), 'title': a.get('title'), 'company': a.get('company_name'), 'company_url': a.get('company_url'), 'amount': a.get('amount'),
                               'date': (a.get('date_published') or '')[:10], 'kind': a.get('kind'), 'path': a.get('rebranding_truncated_path') or a.get('truncated_path'), 'slovo': slovo, 'gruppa': gr, 'regions': a.get('lot_regions')})
            f.write(json.dumps({'klyuch': kl, 'n_items': len(items), 'zapisi': zapisi}, ensure_ascii=False) + '\n'); f.flush(); gotovo.add(kl)
            for z in zapisi:
                if z['id'] not in lenta: lenta[z['id']] = z; n_new += 1
            time.sleep(0.5)
            if len(items) < 200 or TEST: break
f.close()
print(f'лента: закупок края {len(lenta)} (новых {n_new}), страниц {len(gotovo)}', flush=True)
cust = {}
if os.path.exists(F_C):
    for l in open(F_C, encoding='utf-8'):
        try: d = json.loads(l); cust[d['url']] = d
        except Exception: pass
fc = open(F_C, 'a', encoding='utf-8'); n_c = 0
for z in lenta.values():
    cu = z.get('company_url')
    if not cu or cu in cust: continue
    if time.time() - T0 > BUDGET: break
    d = {'url': cu, 'inn': '', 'imya': z.get('company')}
    try:
        r = S.get('https://etpgpb.ru' + cu, headers={'User-Agent': UA['User-Agent']}, timeout=60, verify=False)
        t = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' | ', r.text)))
        m = re.search(r'ИНН\D{0,20}(\d{10,12})', t); d['inn'] = m.group(1) if m else ''
        m = re.search(r'(?:Адрес|Регион)[^|]{0,10}\|[\s|]*([^|]{5,150})', t); d['adres'] = m.group(1).strip() if m else ''
    except Exception as e: d['err'] = repr(e)[:80]
    cust[cu] = d; fc.write(json.dumps(d, ensure_ascii=False) + '\n'); fc.flush(); n_c += 1
    time.sleep(0.5)
fc.close()
print(f'заказчиков в кэше {len(cust)} (за заход {n_c})', flush=True)
c = sqlite3.connect(DB, timeout=120); have = {r[0] for r in c.execute('select inn from predpriyatiya')}; n_f = n_p = 0
for z in lenta.values():
    d = cust.get(z.get('company_url') or '') or {}
    inn = d.get('inn') or ''
    if not inn.startswith('22'): continue
    title = z.get('title') or ''
    if AVTO.search(title): continue
    tip = vid(title)
    if not tip: continue
    if inn not in have:
        c.execute('insert or ignore into predpriyatiya(inn, nazvanie, adres, istochniki_zapisi, ts) values(?,?,?,?,?)', (inn, z.get('company'), d.get('adres', ''), 'gpb', TS)); have.add(inn); n_p += 1
    u = 'https://etpgpb.ru' + (z.get('path') or '')
    cit = (title[:300] + ' | ' + (z.get('nomer') or '') + ' | ' + (z.get('amount') or '') + ' руб | ' + (z.get('date') or ''))[:500]
    c.execute('''insert or ignore into fakty(inn,predpriyatie,vid_fakta,tip,marka_model,sreda,data,srok_do,status_sroka,sila,istochnik,ssylka,citata,kto_sobral,ts,klyuch) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
              (inn, z.get('company'), z['gruppa'], tip, '', '', z.get('date'), '', '', 4 if z['gruppa'] == 'закупка машины' else 5, 'etpgpb.ru', u, cit, 'ak_gpb', TS, f'{inn}|{u}|{tip}||{cit[:80]}')); n_f += 1
c.commit()
print('факты ГПБ:', c.execute("select count(*), count(distinct inn) from fakty where kto_sobral='ak_gpb'").fetchone(), '| новых предприятий', n_p, flush=True)
c.close()
vse_slova = [s for ss in GRUPPY.values() for s in ss]
if not TEST and all(any(k.startswith(s + '|') for k in gotovo) for s in vse_slova) and not [z for z in lenta.values() if z.get('company_url') and z['company_url'] not in cust]: print('ГОТОВО')
