# -*- coding: utf-8 -*-
"""Т2.4в. Площадки по ИНН края: Росэлторг (search_ajax?customer=<ИНН>) и ТЭК-Торг (_next/data ... organizer[]=<ИНН>) +
B2B-Center по словам с привязкой организатора к базе по названию (у площадки нет региона и ИНН в выдаче).
Очередь по ИНН: доказано -> косвенно -> кандидат -> остальные производственные по выручке. Резюм в pl-po-inn.jsonl (ключ ИНН|площадка).
Факты: ссылка на процедуру, цитата = название. argv: [бюджет] [TEST]."""
import os, sys, re, json, time, html, sqlite3, requests
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
requests.packages.urllib3.disable_warnings()
AK = r'C:\sender\_ops\ak'; DB = os.path.join(AK, 'AK-BAZA.sqlite'); F = os.path.join(AK, 'pl-po-inn.jsonl'); F_B2B = os.path.join(AK, 'b2b-lenta.jsonl')
BUDGET = int(sys.argv[1]) if len(sys.argv) > 1 else 1400; TEST = 'TEST' in sys.argv
T0 = time.time(); TS = time.strftime('%Y-%m-%d %H:%M')
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36', 'Accept': '*/*', 'Accept-Language': 'ru', 'X-Requested-With': 'XMLHttpRequest'}
S = requests.Session(); S.headers.update(UA)
MASH = re.compile(r'компрессор|воздуходув|нагнетател|осушител\w+\s+(сжат|возд)|ресивер|воздухосборник|воздухоразделительн|генератор\w*\s+(азота|кислорода)|азотн\w+\s+(станц|установ)|кислородн\w+\s+(станц|установ)|компрессорн|сжат\w+\s+воздух|пневмо', re.I)
AVTO = re.compile(r'автомоб|\bзил\b|камаз|трактор|шасси|тормозн|двигател|кондиционер|холодильн|тепловоз|вагон|локомотив', re.I)
GR = [('закупка ТО', r'обслуживан|ремонт|ревизи|диагност|освидетельств|экспертиз'), ('закупка запчастей', r'запасн|запчаст|ремкомплект|клапан|фильтр|масло|сепаратор|винтов\w+\s+блок|уплотнен'), ('закупка машины', r'.')]
VIDY = [('генератор кислорода', r'кислородн'), ('генератор азота', r'азотн'), ('ВРУ', r'воздухоразделительн'), ('воздуходувка', r'воздуходув'), ('осушитель', r'осушител'), ('ресивер', r'ресивер|воздухосборник'),
        ('компрессорная станция', r'компрессорн\w+\s+станц'), ('компрессор', r'компрессор|пневмо|сжат')]
def vid(s):
    for v, rx in VIDY:
        if re.search(rx, s or '', re.I): return v
    return ''
def razbor_rel(cd):
    """Карточка Росэлторга -> предмет (весь текст ссылки), ИНН и название заказчика, регион, номер, дата."""
    mu = re.search(r'href="(/procedure/[^"]+)"', cd)
    if not mu: return None
    mt = re.search(r'search-results__link--description">(.*?)</a>', cd, re.S)
    title = html.unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', mt.group(1)))).strip() if mt else ''
    minn = re.search(r'/companies/resolve/(\d{10,12})/', cd) or re.search(r"tooltip__inn'>ИНН (\d{10,12})", cd)
    mnaz = re.search(r'link_primary_active[^>]*>\s*([^<]{4,200})', cd)
    mreg = re.search(r'search-results__region">\s*<p[^>]*>([^<]{2,40})', cd)
    num = re.search(r'procedure-number="([\w\d]+)"', cd); dat = re.search(r'(\d{2}\.\d{2}\.\d{4})', cd)
    return {'url': 'https://www.roseltorg.ru' + mu.group(1), 'title': title, 'inn': minn.group(1) if minn else '',
            'zakazchik': html.unescape(mnaz.group(1)).strip() if mnaz else '', 'region': (mreg.group(1) or '').strip() if mreg else '',
            'nomer': num.group(1) if num else '', 'date': dat.group(1) if dat else ''}


def gruppa(s):
    for g, rx in GR:
        if re.search(rx, s or '', re.I): return g
    return 'закупка машины'
c = sqlite3.connect(DB, timeout=120)
vyr = {r[0]: r[1] for r in c.execute("select inn, max(vyruchka_rub) from finansy group by 1")}
CAND = re.compile(r'^(0[1-9]|1\d|2\d|3[0-9]|4[1-3]|45\.2|49|52|71\.12|71\.2|72|77\.3|86\.1)')
pr = c.execute("select inn, klass, okved_osn, nazvanie, nazvanie_polnoe from predpriyatiya where inn like '22%' and (status_egrul is null or status_egrul not like '%LIQUID%')").fetchall()
fk = {r[0] for r in c.execute("select distinct inn from fakty")}
def rang(r):
    inn, kl, ok, *_ = r
    if inn in fk: return 0
    if (kl or '').startswith('косвенно'): return 1
    if (kl or '').startswith('кандидат'): return 2
    if CAND.match(ok or ''): return 3
    return 9
ochered = sorted([r for r in pr if rang(r) < 9], key=lambda r: (rang(r), -(vyr.get(r[0]) or 0)))
imena = {}
def norm(s): return re.sub(r'^(ооо|оао|зао|ао|пао|муп|гуп|фкп|фгуп|ип|кгбу|мбу|мку|нао|кгуп|огуп)\s*', '', re.sub(r'[^а-яёa-z0-9 ]', '', (s or '').lower()).strip()).strip()
for inn, kl, ok, naz, nazp in pr:
    for nm in (naz, nazp):
        k = norm(nm)
        if len(k) >= 6: imena.setdefault(k, inn)
gotovo = set(); zapisi = []
if os.path.exists(F):
    for l in open(F, encoding='utf-8'):
        try: d = json.loads(l); gotovo.add(d['klyuch']); zapisi.append(d)
        except Exception: pass
f = open(F, 'a', encoding='utf-8'); n_r = n_t = 0
try:
    r = S.get('https://www.tektorg.ru/procedures', timeout=60, verify=False); BID = re.search(r'"buildId":"([^"]+)"', r.text).group(1)
except Exception: BID = ''
SLOVA_MASH = ['компрессор', 'компрессорная станция', 'компрессорная установка', 'винтовой компрессор', 'поршневой компрессор', 'воздуходувка', 'нагнетатель воздуха',
              'осушитель сжатого воздуха', 'ресивер', 'воздухосборник', 'генератор азота', 'генератор кислорода', 'азотная станция', 'кислородная станция',
              'воздухоразделительная установка', 'сжатый воздух', 'ремонт компрессора', 'обслуживание компрессора', 'запчасти компрессор', 'масло компрессорное', 'винтовой блок']
if 'SLOVA' in sys.argv:
    F_S = os.path.join(AK, 'rel-slova.jsonl'); gs = set(); rows_s = []
    if os.path.exists(F_S):
        for l in open(F_S, encoding='utf-8'):
            try: d0 = json.loads(l); gs.add(d0['klyuch']); rows_s += d0.get('rows', [])
            except Exception: pass
    fs = open(F_S, 'a', encoding='utf-8'); n_s = 0
    for slovo in (SLOVA_MASH[:1] if TEST else SLOVA_MASH):
        for pg in range(0, 60):
            kl = f'{slovo}|{pg}'
            if kl in gs: continue
            if time.time() - T0 > BUDGET: break
            try:
                r = S.get('https://www.roseltorg.ru/procedures/search_ajax', params={'query_field': slovo, 'region[]': '22', 'page': pg}, timeout=60, verify=False); t = r.text
            except Exception: break
            cards = re.split(r'<div class="search-results__item', t)[1:]
            rows = [x for x in (razbor_rel(cd) for cd in cards) if x]
            fs.write(json.dumps({'klyuch': kl, 'rows': rows}, ensure_ascii=False) + '\n'); fs.flush(); gs.add(kl); rows_s += rows; n_s += len(rows)
            time.sleep(0.5)
            if len(cards) < 10 or TEST: break
    fs.close()
    c2 = sqlite3.connect(DB, timeout=120); have2 = {r[0] for r in c2.execute('select inn from predpriyatiya')}; n_f2 = n_p2 = 0
    for x in rows_s:
        inn = x.get('inn') or ''
        if not inn.startswith('22') or '22.' not in (x.get('region') or '22. '): 
            if not inn.startswith('22'): continue
        tl = x['title']
        if not MASH.search(tl) or AVTO.search(tl): continue
        tip = vid(tl)
        if not tip: continue
        if inn not in have2:
            c2.execute('insert or ignore into predpriyatiya(inn, nazvanie, istochniki_zapisi, ts) values(?,?,?,?)', (inn, x.get('zakazchik'), 'roseltorg', TS)); have2.add(inn); n_p2 += 1
        gr = gruppa(tl); cit = (tl[:350] + ' | ' + (x.get('nomer') or '') + ' | ' + (x.get('date') or '') + ' | ' + (x.get('region') or ''))[:500]
        c2.execute('''insert or ignore into fakty(inn,predpriyatie,vid_fakta,tip,marka_model,sreda,data,srok_do,status_sroka,sila,istochnik,ssylka,citata,kto_sobral,ts,klyuch) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                   (inn, x.get('zakazchik'), gr, tip, '', '', x.get('date'), '', '', 4 if gr == 'закупка машины' else 5, 'roseltorg.ru', x['url'], cit, 'ak_rel_slova', TS, f'{inn}|{x["url"]}|{tip}||{cit[:80]}')); n_f2 += 1
    c2.commit()
    print('Росэлторг по словам: строк', len(rows_s), '(за заход', n_s, ') | фактов', c2.execute("select count(*), count(distinct inn) from fakty where kto_sobral='ak_rel_slova'").fetchone(), '| новых предприятий', n_p2, flush=True)
    c2.close()
    if all(f'{sl}|0' in gs for sl in SLOVA_MASH) and not TEST: print('ГОТОВО')
    sys.exit(0)
if TEST: ochered = ochered[:5]
print(f'очередь ИНН {len(ochered)} (готово ключей {len(gotovo)}), tektorg buildId {"есть" if BID else "НЕТ"}', flush=True)
for inn, kl, ok, naz, nazp in ochered:
    if time.time() - T0 > BUDGET: break
    # Росэлторг
    kl_r = f'{inn}|roseltorg'
    if kl_r not in gotovo:
        items = []; err = ''
        for pg in range(0, 30):
            try:
                r = S.get(f'https://www.roseltorg.ru/procedures/search_ajax?customer={inn}&page={pg}', timeout=60, verify=False); t = r.text
            except Exception as e: err = repr(e)[:60]; break
            cards = re.split(r'<div class="search-results__item', t)[1:]
            if not cards: break
            for cd in cards:
                x = razbor_rel(cd)
                if x: items.append(x)
            time.sleep(0.4)
            if len(cards) < 10: break
        mash = [x for x in items if MASH.search(x['title']) and not AVTO.search(x['title'])]
        d = {'klyuch': kl_r, 'inn': inn, 'ploshchadka': 'roseltorg', 'vsego': len(items), 'mashina': mash, 'err': err}
        f.write(json.dumps(d, ensure_ascii=False) + '\n'); f.flush(); gotovo.add(kl_r); zapisi.append(d); n_r += 1
    # ТЭК-Торг
    kl_t = f'{inn}|tektorg'
    if BID and kl_t not in gotovo:
        items = []; err = ''
        for pg in range(1, 40):
            try:
                r = S.get(f'https://www.tektorg.ru/_next/data/{BID}/ru/procedures.json?organizer[]={inn}&page={pg}', timeout=60, verify=False)
                lp = (((r.json().get('pageProps') or {}).get('initialReduxState') or {}).get('listingProcedures') or {})
            except Exception as e: err = repr(e)[:60]; break
            for d0 in lp.get('data') or []:
                items.append({'url': d0.get('etpLink') or f'https://www.tektorg.ru/procedures/{d0.get("id")}', 'title': d0.get('title') or '', 'date': str((d0.get('dates') or {}).get('datePublished') or '')[:10], 'nomer': d0.get('registryNumber') or '', 'okpd2': str(d0.get('okpd2') or '')[:60]})
            time.sleep(0.3)
            if pg >= (lp.get('totalPages') or 1): break
        mash = [x for x in items if (MASH.search(x['title']) or x.get('okpd2', '').startswith('28.13')) and not AVTO.search(x['title'])]
        d = {'klyuch': kl_t, 'inn': inn, 'ploshchadka': 'tektorg', 'vsego': len(items), 'mashina': mash, 'err': err}
        f.write(json.dumps(d, ensure_ascii=False) + '\n'); f.flush(); gotovo.add(kl_t); zapisi.append(d); n_t += 1
f.close()
print(f'за заход: roseltorg {n_r}, tektorg {n_t} ИНН | всего записей {len(zapisi)}', flush=True)
# ---- B2B-Center по словам, организатор -> ИНН по названию
b2b_gotovo = set(); b2b = []
if os.path.exists(F_B2B):
    for l in open(F_B2B, encoding='utf-8'):
        try: d = json.loads(l); b2b_gotovo.add(d['klyuch']); b2b += d.get('rows', [])
        except Exception: pass
fb = open(F_B2B, 'a', encoding='utf-8')
for slovo in (['компрессор'] if TEST else ['компрессор', 'воздуходувка', 'осушитель сжатого воздуха', 'ресивер воздушный', 'компрессорная станция', 'генератор азота', 'винтовой блок']):
    for pg in range(1, 40):
        kl = f'{slovo}|{pg}'
        if kl in b2b_gotovo: continue
        if time.time() - T0 > BUDGET: break
        try:
            r = S.get('https://www.b2b-center.ru/market/', params={'searching': 1, 'f_keyword': slovo, 'trade': 'buy', 'from': (pg - 1) * 20}, headers={'X-Requested-With': ''}, timeout=60, verify=False); t = r.text
        except Exception as e: break
        rows = []
        for rw in re.findall(r'<tr[^>]*>(.*?)</tr>', t, re.S):
            mu = re.search(r'href="((?:/app/market-next|/market)/[^"#]+/tender-(\d+)/)', rw); org = re.search(r'href="/firms/([^"]+)"[^>]*>([^<]{3,150})<', rw)
            if not mu or not org: continue
            title = re.search(r'search-results-title-desc">(.*?)</div>', rw, re.S); title = html.unescape(re.sub(r'<[^>]+>', ' ', title.group(1))) if title else ''
            title = re.sub(r'\s+', ' ', title).strip()[:300]
            dat = re.search(r'(\d{2}\.\d{2}\.\d{4})', rw)
            rows.append({'url': 'https://www.b2b-center.ru' + mu.group(1), 'nomer': mu.group(2), 'title': title, 'org': html.unescape(org.group(2)).strip(), 'org_url': org.group(1), 'date': dat.group(1) if dat else '', 'slovo': slovo})
        fb.write(json.dumps({'klyuch': kl, 'rows': rows}, ensure_ascii=False) + '\n'); fb.flush(); b2b_gotovo.add(kl); b2b += rows
        time.sleep(0.6)
        if len(rows) < 15 or TEST: break
fb.close()
# ---- факты
have = {r[0] for r in c.execute('select inn from predpriyatiya')}; n_f = 0
def fakt(inn, naz, x, ist, gr):
    global n_f
    tip = vid(x['title'])
    if not tip: return
    cit = (x['title'][:350] + ' | ' + (x.get('nomer') or '') + ' | ' + (x.get('date') or ''))[:500]
    c.execute('''insert or ignore into fakty(inn,predpriyatie,vid_fakta,tip,marka_model,sreda,data,srok_do,status_sroka,sila,istochnik,ssylka,citata,kto_sobral,ts,klyuch) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
              (inn, naz, gr, tip, '', '', x.get('date') or '', '', '', 4 if gr == 'закупка машины' else 5, ist, x['url'], cit, 'ak_ploshchadki', TS, f'{inn}|{x["url"]}|{tip}||{cit[:80]}')); n_f += 1
naz_po_inn = {r[0]: (r[3] or r[4]) for r in pr}
for d in zapisi:
    for x in d.get('mashina') or []:
        fakt(d['inn'], naz_po_inn.get(d['inn']), x, 'roseltorg.ru' if d['ploshchadka'] == 'roseltorg' else 'tektorg.ru', gruppa(x['title']))
n_b2b = 0
for x in b2b:
    k = norm(x['org']); inn = imena.get(k)
    if not inn or not (MASH.search(x['title']) and not AVTO.search(x['title'])): continue
    fakt(inn, x['org'], x, 'b2b-center.ru', gruppa(x['title'])); n_b2b += 1
c.commit()
print('факты площадок:', c.execute("select istochnik, count(*), count(distinct inn) from fakty where kto_sobral='ak_ploshchadki' group by 1").fetchall(), '| b2b строк', len(b2b), 'привязано к краю', n_b2b, flush=True)
c.close()
if not TEST and all(f'{r[0]}|roseltorg' in gotovo and (not BID or f'{r[0]}|tektorg' in gotovo) for r in ochered): print('ГОТОВО')
