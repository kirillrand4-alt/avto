# -*- coding: utf-8 -*-
"""Т2.4б. torgi.gov.ru: лоты по Алтайскому краю (subjectRFCode=22) со словами машин: продавец/должник = бывший владелец машины.
API JSON: /new/api/public/lotcards/search?text=..&subjectRFCode=22&size=100&page=N. Карточка лота: /new/api/public/lotcards/{id}. Резюм по (слово, страница) в torgi-lenta.jsonl.
Факты: ссылка = https://torgi.gov.ru/new/public/lots/lot/{id} (страница лота), цитата = название лота + описание. ИНН должника/собственника: из карточки лота (attributes) либо DaData по имени. argv: [бюджет] [TEST]."""
import os, sys, re, json, time, sqlite3, requests
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
requests.packages.urllib3.disable_warnings()
AK = r'C:\sender\_ops\ak'; DB = os.path.join(AK, 'AK-BAZA.sqlite')
F_L = os.path.join(AK, 'torgi-lenta.jsonl'); F_K = os.path.join(AK, 'torgi-kartochki.jsonl'); F_D = os.path.join(AK, 'torgi-dadata.jsonl')
BUDGET = int(sys.argv[1]) if len(sys.argv) > 1 else 1400; TEST = 'TEST' in sys.argv
T0 = time.time(); TS = time.strftime('%Y-%m-%d %H:%M')
SLOVA = ['компрессор', 'компрессорная', 'воздуходувка', 'ресивер', 'воздухосборник', 'осушитель воздуха', 'азотная станция', 'кислородная станция', 'нагнетатель']
if TEST: SLOVA = ['компрессор']
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0', 'Accept': 'application/json'}
AVTO = re.compile(r'автомоб|\bзил\b|камаз|\bгаз-|\bпаз\b|\bуаз\b|трактор|шасси|тормозн|двигател|кондиционер', re.I)
HOLOD = re.compile(r'холодильн|фреон|морозильн|витрин', re.I)
def get_json(url, tries=3):
    for i in range(tries):
        try:
            r = requests.get(url, headers=UA, timeout=60, verify=False)
            if r.status_code == 200: return r.json()
            time.sleep(2 + 3 * i)
        except Exception: time.sleep(2 + 3 * i)
    return None
gotovo = set(); lots = {}
if os.path.exists(F_L):
    for l in open(F_L, encoding='utf-8'):
        try: d = json.loads(l)
        except Exception: continue
        gotovo.add(d['klyuch'])
        for x in d.get('lots', []): lots.setdefault(x['id'], x)
f = open(F_L, 'a', encoding='utf-8')
for slovo in SLOVA:
    for pg in range(0, 50):
        kl = f'{slovo}|{pg}'
        if kl in gotovo: continue
        if time.time() - T0 > BUDGET: break
        j = get_json(f'https://torgi.gov.ru/new/api/public/lotcards/search?text={requests.utils.quote(slovo)}&subjectRFCode=22&byFirstVersion=true&size=100&page={pg}')
        if not j: break
        out = [{'id': it.get('id'), 'lotName': it.get('lotName'), 'lotDescription': (it.get('lotDescription') or '')[:600], 'biddType': (it.get('biddType') or {}).get('name'), 'status': it.get('lotStatus'),
                'date': it.get('noticeFirstVersionPublicationDate') or it.get('createDate'), 'price': it.get('priceMin'), 'slovo': slovo, 'subject': it.get('subjectRFCode')} for it in j.get('content', [])]
        f.write(json.dumps({'klyuch': kl, 'total': j.get('totalElements'), 'lots': out}, ensure_ascii=False) + '\n'); f.flush(); gotovo.add(kl)
        for x in out: lots.setdefault(x['id'], x)
        time.sleep(0.4)
        if j.get('last') or not out or TEST: break
f.close()
print(f'лента: лотов {len(lots)}, страниц {len(gotovo)}', flush=True)
# карточки: ищем ИНН и собственника/должника
kart = {}
if os.path.exists(F_K):
    for l in open(F_K, encoding='utf-8'):
        try: d = json.loads(l); kart[d['id']] = d
        except Exception: pass
fk = open(F_K, 'a', encoding='utf-8'); n_k = 0
MASH = re.compile(r'компрессор|воздуходув|ресивер|воздухосборник|осушител|азотн\w+ станц|кислородн\w+ станц|нагнетател', re.I)
for lid, x in lots.items():
    if lid in kart: continue
    if time.time() - T0 > BUDGET: break
    tekst = (x.get('lotName') or '') + ' ' + (x.get('lotDescription') or '')
    if not MASH.search(tekst) or AVTO.search(tekst):
        kart[lid] = {'id': lid, 'skip': True}; fk.write(json.dumps(kart[lid], ensure_ascii=False) + '\n'); continue
    j = get_json(f'https://torgi.gov.ru/new/api/public/lotcards/{lid}')
    d = {'id': lid, 'inn': '', 'vladelec': '', 'org': '', 'attrs': []}
    if j:
        s = json.dumps(j, ensure_ascii=False)
        inns = sorted(set(re.findall(r'"(?:inn|INN|debtorInn|ownerInn|organizationInn)"\s*:\s*"?(\d{10,12})', s)))
        d['inn_vse'] = inns
        for a in (j.get('attributes') or []):
            nm = (a.get('fullName') or a.get('name') or ''); val = a.get('value')
            if isinstance(val, dict): val = val.get('name') or val.get('value') or json.dumps(val, ensure_ascii=False)[:100]
            d['attrs'].append(f'{nm}: {val}'[:200])
            if re.search(r'ИНН', nm, re.I) and re.search(r'\d{10,12}', str(val)): d['inn'] = re.search(r'\d{10,12}', str(val)).group(0)
            if re.search(r'должник|собственник|правообладател|балансодержател', nm, re.I) and not d['vladelec']: d['vladelec'] = str(val)[:200]
        org = j.get('bidderOrg') or j.get('organizerOrg') or {}
        d['org'] = (org.get('fullName') or org.get('name') or '')[:200] if isinstance(org, dict) else ''
        if not d['inn'] and str(j.get('depositRecipientINN') or '').startswith('22'):
            d['inn'] = str(j.get('depositRecipientINN')); d['vladelec'] = d['vladelec'] or (j.get('depositRecipientName') or '') + ' (получатель задатка/организатор)'
        d['estateAddress'] = (j.get('estateAddress') or '')[:200]
        m = re.search(r'(?:должник|собственник|правообладател|балансодержател)[^"]{0,60}"?[:\s]*"?([^"]{5,150})', s, re.I)
        if m and not d['vladelec']: d['vladelec'] = m.group(1)
        d['dolzhnik_inn_kandidat'] = [i for i in inns if i.startswith('22')]
    kart[lid] = d; fk.write(json.dumps(d, ensure_ascii=False) + '\n'); fk.flush(); n_k += 1
    time.sleep(0.5)
fk.close()
print(f'карточек за заход {n_k}, всего {len(kart)}', flush=True)
# факты
c = sqlite3.connect(DB, timeout=120); have = {r[0] for r in c.execute('select inn from predpriyatiya')}; n_f = 0
for lid, d in kart.items():
    if d.get('skip'): continue
    x = lots.get(lid, {})
    inn = d.get('inn') or (d.get('dolzhnik_inn_kandidat') or [''])[0]
    if not inn.startswith('22'): continue
    tekst = (x.get('lotName') or '') + ' | ' + (x.get('lotDescription') or '')
    tip = 'холодильный компрессор' if HOLOD.search(tekst) and not re.search(r'сжат|винтов|пневм', tekst, re.I) else 'компрессор'
    for v, rx in [('воздуходувка', r'воздуходув'), ('ресивер', r'ресивер|воздухосборник'), ('осушитель', r'осушител'), ('компрессорная станция', r'компрессорн\w+ станц')]:
        if re.search(rx, tekst, re.I) and tip == 'компрессор': tip = v
    if inn not in have:
        c.execute('insert or ignore into predpriyatiya(inn, nazvanie, istochniki_zapisi, ts) values(?,?,?,?)', (inn, d.get('vladelec') or d.get('org'), 'torgi', TS)); have.add(inn)
    u = f'https://torgi.gov.ru/new/public/lots/lot/{lid}'
    cit = (tekst[:350] + ' | ' + (x.get('biddType') or '') + ' | ' + (d.get('vladelec') or ''))[:500]
    c.execute('''insert or ignore into fakty(inn,predpriyatie,vid_fakta,tip,marka_model,sreda,data,srok_do,status_sroka,sila,istochnik,ssylka,citata,kto_sobral,ts,klyuch) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
              (inn, d.get('vladelec') or d.get('org'), 'лот torgi (была машина)', tip, '', '', (x.get('date') or '')[:10], '', '', 3, 'torgi.gov.ru', u, cit, 'ak_torgi', TS, f'{inn}|{u}|{tip}||{cit[:80]}')); n_f += 1
c.commit()
print('факты torgi:', c.execute("select count(*) from fakty where kto_sobral='ak_torgi'").fetchone()[0], '| ИНН:', c.execute("select count(distinct inn) from fakty where kto_sobral='ak_torgi'").fetchone()[0], flush=True)
c.close()
if not TEST and all(f'{s}|0' in gotovo for s in SLOVA) and not [l for l in lots if l not in kart]: print('ГОТОВО')
