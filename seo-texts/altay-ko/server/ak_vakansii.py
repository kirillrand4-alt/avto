# -*- coding: utf-8 -*-
"""Т2.5. Вакансии как доказательство машины: «Работа России» (регион 2200000000000) и hh.ru (area Алтайский край, токен приложения).
Резюм по (источник, слово, страница) в vak-lenta.jsonl. Факты в AK-BAZA.fakty: ссылка на API/карточку вакансии, цитата = должность + кусок обязанностей.
hh не отдаёт ИНН: работодатель -> DaData по имени с фильтром края (кэш vak-dadata.jsonl). argv: [бюджет] [TEST]."""
import os, sys, re, json, time, sqlite3, requests
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
requests.packages.urllib3.disable_warnings()
AK = r'C:\sender\_ops\ak'; DB = os.path.join(AK, 'AK-BAZA.sqlite')
F_L = os.path.join(AK, 'vak-lenta.jsonl'); F_D = os.path.join(AK, 'vak-dadata.jsonl')
BUDGET = int(sys.argv[1]) if len(sys.argv) > 1 else 1400; TEST = 'TEST' in sys.argv
T0 = time.time(); TS = time.strftime('%Y-%m-%d %H:%M')
SLOVA = ['компрессор', 'компрессорных установок', 'машинист компрессорных', 'компрессорной станции', 'компрессорного оборудования', 'воздухоразделительных установок',
         'аппаратчик воздухоразделения', 'слесарь по ремонту компрессорного', 'машинист воздуходувки', 'пневмооборудование', 'сжатого воздуха', 'азотной станции', 'кислородной станции',
         'машинист холодильных установок', 'компрессорщик']
if TEST: SLOVA = ['машинист компрессорных']
MASH = re.compile(r'компрессор|воздуходув|воздухоразделительн|сжат\w+ воздух|пневмо|азотн\w+ станц|кислородн\w+ станц', re.I)
PRYAMOE = re.compile(r'машинист\w* компрессорн|компрессорн\w+ (установ|станц|цех)|аппаратчик воздухоразделен|слесарь\w* .{0,40}компрессор|машинист воздуходув|компрессорщик', re.I)
HOLOD = re.compile(r'холодильн|фреон|хладон|рефриж', re.I)
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0'}
DTOK = os.environ.get('DADATA_TOKEN', ''); HHTOK = os.environ.get('HH_APP_TOKEN', '')
gotovo = set(); vak = {}
if os.path.exists(F_L):
    for l in open(F_L, encoding='utf-8'):
        try: d = json.loads(l)
        except Exception: continue
        gotovo.add(d['klyuch'])
        for v in d.get('vakansii', []): vak.setdefault(v['url'], v)
f = open(F_L, 'a', encoding='utf-8'); n_new = 0
# ---- Работа России
for slovo in SLOVA:
    for off in range(0, 40):
        kl = f'trudvsem|{slovo}|{off}'
        if kl in gotovo: continue
        if time.time() - T0 > BUDGET: break
        try:
            r = requests.get(f'http://opendata.trudvsem.ru/api/v1/vacancies/region/2200000000000?text={requests.utils.quote(slovo)}&limit=100&offset={off}', headers=UA, timeout=60)
            j = r.json()
        except Exception as e:
            print('trudvsem err', slovo, off, repr(e)[:80]); time.sleep(5); continue
        vs = ((j.get('results') or {}).get('vacancies') or [])
        out = []
        for x in vs:
            v = x.get('vacancy') or {}; comp = v.get('company') or {}
            out.append({'url': v.get('vac_url') or f'trudvsem:{v.get("id")}', 'istochnik': 'trudvsem', 'slovo': slovo, 'inn': comp.get('inn') or '', 'rabotodatel': comp.get('name') or '',
                        'dolzhnost': v.get('job-name') or '', 'obyazannosti': re.sub(r'<[^>]+>', ' ', (v.get('duty') or ''))[:600], 'data': v.get('creation-date') or '', 'region': (v.get('region') or {}).get('name', ''),
                        'kontakt': (v.get('contact_person') or ''), 'kontakty': json.dumps(v.get('contact_list') or [], ensure_ascii=False)[:300], 'api': f'http://opendata.trudvsem.ru/api/v1/vacancies/company/inn/{comp.get("inn")}?limit=100' if comp.get('inn') else ''})
        f.write(json.dumps({'klyuch': kl, 'vakansii': out, 'total': (j.get('meta') or {}).get('total')}, ensure_ascii=False) + '\n'); f.flush(); gotovo.add(kl)
        for v in out:
            if v['url'] not in vak: vak[v['url']] = v; n_new += 1
        time.sleep(0.5)
        if len(vs) < 100 or TEST: break
# ---- hh.ru
hh_ok = None
if HHTOK:
    H = {'User-Agent': 'prokompressor-research/1.0 (info@prokompressor.ru)', 'Authorization': 'Bearer ' + HHTOK}
    for slovo in SLOVA:
        for pg in range(0, 20):
            kl = f'hh|{slovo}|{pg}'
            if kl in gotovo: continue
            if time.time() - T0 > BUDGET: break
            try:
                r = requests.get('https://api.hh.ru/vacancies', params={'text': slovo, 'area': 1217, 'per_page': 100, 'page': pg, 'search_field': ['name', 'description']}, headers=H, timeout=60)
                if hh_ok is None: hh_ok = r.status_code; print('hh статус', r.status_code, r.text[:120] if r.status_code != 200 else '', flush=True)
                if r.status_code != 200: break
                j = r.json()
            except Exception as e:
                print('hh err', repr(e)[:80]); break
            out = []
            for v in j.get('items') or []:
                emp = v.get('employer') or {}; sn = v.get('snippet') or {}
                out.append({'url': v.get('alternate_url') or v.get('url'), 'istochnik': 'hh', 'slovo': slovo, 'inn': '', 'rabotodatel': emp.get('name') or '', 'hh_employer': emp.get('id'),
                            'dolzhnost': v.get('name') or '', 'obyazannosti': re.sub(r'<[^>]+>', ' ', (sn.get('responsibility') or '') + ' ' + (sn.get('requirement') or ''))[:600], 'data': v.get('published_at') or '',
                            'region': (v.get('area') or {}).get('name', ''), 'kontakt': '', 'kontakty': '', 'api': v.get('url') or ''})
            f.write(json.dumps({'klyuch': kl, 'vakansii': out, 'total': j.get('found')}, ensure_ascii=False) + '\n'); f.flush(); gotovo.add(kl)
            for v in out:
                if v['url'] not in vak: vak[v['url']] = v; n_new += 1
            time.sleep(0.4)
            if pg + 1 >= (j.get('pages') or 1) or TEST: break
else:
    print('hh: токена нет', flush=True)
f.close()
print(f'вакансий всего {len(vak)} (новых {n_new}); trudvsem {sum(1 for v in vak.values() if v["istochnik"]=="trudvsem")}, hh {sum(1 for v in vak.values() if v["istochnik"]=="hh")}', flush=True)
# ---- ИНН через DaData для hh
dd = {}
if os.path.exists(F_D):
    for l in open(F_D, encoding='utf-8'):
        try: d = json.loads(l); dd[d['imya']] = d
        except Exception: pass
def dadata_imya(imya):
    if imya in dd: return dd[imya]
    d = {'imya': imya, 'inn': '', 'nazvanie': ''}
    if DTOK and imya:
        try:
            r = requests.post('https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/party', json={'query': imya, 'count': 3, 'locations': [{'kladr_id': '2200000000000'}]},
                              headers={'Content-Type': 'application/json', 'Accept': 'application/json', 'Authorization': 'Token ' + DTOK}, timeout=30)
            for sug in (r.json().get('suggestions') or []):
                dat = sug.get('data') or {}
                if str(dat.get('inn', '')).startswith('22'):
                    d.update({'inn': dat.get('inn'), 'nazvanie': sug.get('value')}); break
        except Exception as e: d['err'] = repr(e)[:80]
    dd[imya] = d
    with open(F_D, 'a', encoding='utf-8') as ff: ff.write(json.dumps(d, ensure_ascii=False) + '\n')
    return d
# ---- факты
c = sqlite3.connect(DB, timeout=120); have = {r[0] for r in c.execute('select inn from predpriyatiya')}
n_f = n_p = 0; n_dd = 0
for u, v in vak.items():
    tekst = (v['dolzhnost'] or '') + ' | ' + (v['obyazannosti'] or '')
    if not MASH.search(tekst): continue
    inn = v.get('inn') or ''
    if not inn and v['istochnik'] == 'hh':
        r = dadata_imya(v['rabotodatel']); inn = r.get('inn') or ''; n_dd += 1 if inn else 0
    if not inn.startswith('22'): continue
    pr = bool(PRYAMOE.search(tekst)); hol = bool(HOLOD.search(tekst)) and not re.search(r'сжат\w+ воздух|пневмо', tekst, re.I)
    tip = 'холодильный компрессор' if hol else ('компрессорная установка' if pr else 'компрессор')
    sila = 2 if hol else (4 if pr else 3)
    if inn not in have:
        c.execute('insert or ignore into predpriyatiya(inn, nazvanie, istochniki_zapisi, ts) values(?,?,?,?)', (inn, v['rabotodatel'], 'vakansii', TS)); have.add(inn); n_p += 1
    cit = (v['dolzhnost'] + ' | ' + re.sub(r'\s+', ' ', v['obyazannosti'])[:300] + (' | ' + v['data'] if v['data'] else ''))[:500]
    kl = f'{inn}|{u}|{tip}||{cit[:80]}'
    c.execute('''insert or ignore into fakty(inn,predpriyatie,vid_fakta,tip,marka_model,sreda,data,srok_do,status_sroka,sila,istochnik,ssylka,citata,kto_sobral,ts,klyuch) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
              (inn, v['rabotodatel'], 'вакансия', tip, '', '', v['data'][:10], '', '', sila, v['istochnik'] + ('.ru' if v['istochnik']=='hh' else '.ru'), v.get('api') or u, cit, 'ak_vakansii', TS, kl)); n_f += 1
c.commit()
print('факты вакансий (кандидатов)', n_f, '| dadata ИНН', n_dd, '| новых предприятий', n_p, '| фактов ak_vakansii всего', c.execute("select count(*) from fakty where kto_sobral='ak_vakansii'").fetchone()[0], '| ИНН с вакансией', c.execute("select count(distinct inn) from fakty where vid_fakta='вакансия'").fetchone()[0], flush=True)
c.close()
if not TEST: print('ГОТОВО')
