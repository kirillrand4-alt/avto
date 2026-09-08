# -*- coding: utf-8 -*-
"""Т1.2. ГИР БО (bo.nalog.gov.ru) как знаменатель и первоисточник финансов по Алтайскому краю.
Этап 1: список организаций по адресу «Алтайский край» (все периоды) -> girbo-spisok.jsonl (резюм по странице).
Этап 2: по каждому id -> /nbo/organizations/{id}/bfo/ -> girbo-bfo.jsonl (резюм по id), 4 потока, бюджет.
Этап 3: влив в AK-BAZA.sqlite (predpriyatiya + finansy), идемпотентно.
Печатает ГОТОВО, когда этап 2 завершён. argv: [бюджет_сек]"""
import os, sys, re, json, time, sqlite3, threading, requests
from concurrent.futures import ThreadPoolExecutor
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
requests.packages.urllib3.disable_warnings()
AK = r'C:\sender\_ops\ak'; DB = os.path.join(AK, 'AK-BAZA.sqlite')
F_SP = os.path.join(AK, 'girbo-spisok.jsonl'); F_BFO = os.path.join(AK, 'girbo-bfo.jsonl')
BUDGET = int(sys.argv[1]) if len(sys.argv) > 1 else 1400
T0 = time.time()
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36', 'Accept': 'application/json'}
S = requests.Session(); S.headers.update(UA)
lock = threading.Lock()
def strip(s): return re.sub(r'</?strong>', '', s or '')
def get_json(url, tries=3):
    for i in range(tries):
        try:
            r = S.get(url, timeout=60, verify=False)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (404,):
                return None
            time.sleep(2 + 3 * i)
        except Exception:
            time.sleep(2 + 3 * i)
    return 'ERR'
# ---- этап 1: список по адресу, разрезанный по ОКВЭД (API отдаёт не больше 100 страниц = 10 000 записей на запрос)
done_parts = set(); spisok = {}
if os.path.exists(F_SP):
    for l in open(F_SP, encoding='utf-8'):
        try: d = json.loads(l)
        except Exception: continue
        if d.get('gotovo'): done_parts.add(d['part'])
        for it in d.get('items', []): spisok[it['id']] = it
ADRES = '%D0%90%D0%BB%D1%82%D0%B0%D0%B9%D1%81%D0%BA%D0%B8%D0%B9%20%D0%BA%D1%80%D0%B0%D0%B9'
def part_url(part, pg): return f'https://bo.nalog.gov.ru/advanced-search/organizations?address={ADRES}&okved={part}&size=100&page={pg}'
def items_of(jj):
    return [{'id': it.get('id'), 'inn': strip(it.get('inn')), 'ogrn': strip(it.get('ogrn')), 'nazvanie': strip(it.get('shortName')),
             'okved': strip(it.get('okved2')) if isinstance(it.get('okved2'), str) else (it.get('okved2') or {}).get('id'),
             'region': strip(it.get('region')), 'city': strip(it.get('city') or it.get('settlement') or ''), 'district': strip(it.get('district') or ''), 'index': it.get('index')} for it in jj.get('content', [])]
f = open(F_SP, 'a', encoding='utf-8')
ochered_parts = [f'{i:02d}' for i in range(1, 100)]
n_parts_done = 0
while ochered_parts and time.time() - T0 < BUDGET:
    part = ochered_parts.pop(0)
    if part in done_parts: continue
    j = get_json(part_url(part, 0))
    if not isinstance(j, dict): continue
    tp = j.get('totalPages') or 0; te = j.get('totalElements') or 0
    if tp > 100:
        # слишком крупный раздел: дробим на подкоды
        sub = [f'{part}.{k}' for k in range(0, 10)] if part.count('.') == 0 else [f'{part}{k}' for k in range(0, 10)]
        ochered_parts = sub + ochered_parts
        print(f'  раздел {part}: {te} записей, {tp} страниц - дроблю', flush=True); continue
    items = items_of(j)
    for pg in range(1, tp):
        if time.time() - T0 > BUDGET: break
        jj = get_json(part_url(part, pg))
        if isinstance(jj, dict): items += items_of(jj)
        else: break
    else:
        pass
    polnyy = (tp <= 1) or (len(items) >= te * 0.95)
    f.write(json.dumps({'part': part, 'total': te, 'gotovo': polnyy, 'items': items}, ensure_ascii=False) + '\n'); f.flush()
    for it in items: spisok[it['id']] = it
    if polnyy: done_parts.add(part); n_parts_done += 1
f.close()
total_pages = None
print(f'этап 1: разделов готово за заход {n_parts_done}, всего готово {len(done_parts)}, в очереди {len(ochered_parts)} | организаций {len(spisok)}', flush=True)
spisok_polon = not ochered_parts
# ---- этап 2
done_ids = set()
if os.path.exists(F_BFO):
    for l in open(F_BFO, encoding='utf-8'):
        try: done_ids.add(json.loads(l)['id'])
        except Exception: pass
ochered = [i for i in spisok if i not in done_ids]
print('этап 2: bfo готово', len(done_ids), 'в очереди', len(ochered), flush=True)
fb = open(F_BFO, 'a', encoding='utf-8')
schet = {'ok': 0, 'pusto': 0, 'err': 0}
def odin(oid):
    if time.time() - T0 > BUDGET: return
    j = get_json(f'https://bo.nalog.gov.ru/nbo/organizations/{oid}/bfo/')
    if j == 'ERR':
        with lock:
            schet['err'] += 1
            if schet['err'] > 200: return
        return
    it = spisok[oid]; periods = []
    for b in (j or []):
        tc = (b.get('typeCorrections') or [{}])[0].get('correction') or {}
        fr = tc.get('financialResult') or {}; fm = tc.get('fundsMovement') or {}; bal = tc.get('balance') or {}
        oi = b.get('organizationInfo') or {}
        periods.append({'period': b.get('period'), 'gainSum': b.get('gainSum'), 'v2110': fr.get('current2110'), 'p2400': fr.get('current2400'), 'n2410': fr.get('current2410'),
                        'n4124': fm.get('current4124'), 'aktivy1600': bal.get('current1600'), 'msp': b.get('mspCategory'), 'adres': oi.get('address'), 'okved': (oi.get('okved2') or {}).get('id') if isinstance(oi.get('okved2'), dict) else oi.get('okved2_id'),
                        'okopf': (oi.get('okopf') or {}).get('name') if isinstance(oi.get('okopf'), dict) else None, 'fullName': oi.get('fullName'), 'kpp': oi.get('kpp')})
    with lock:
        fb.write(json.dumps({'id': oid, 'inn': it['inn'], 'periods': periods}, ensure_ascii=False) + '\n'); fb.flush()
        schet['ok' if periods else 'pusto'] += 1
with ThreadPoolExecutor(4) as ex:
    list(ex.map(odin, ochered))
    
fb.close()
print('этап 2 за заход:', schet, '| прошло', round(time.time() - T0), 'с', flush=True)
# ---- этап 3: влив
c = sqlite3.connect(DB, timeout=120)
cols = [d[1] for d in c.execute('pragma table_info(predpriyatiya)')]
TS = time.strftime('%Y-%m-%d %H:%M')
n_new = n_fin = 0
have = {r[0] for r in c.execute('select inn from predpriyatiya')}
for l in open(F_BFO, encoding='utf-8'):
    try: d = json.loads(l)
    except Exception: continue
    inn = d['inn']; it = spisok.get(d['id']) or {}
    if not inn or len(inn) not in (10, 12): continue
    last = d['periods'][-1] if d['periods'] else {}
    adres = last.get('adres') or ''
    if re.search(r'респ\w*\.?\s*алтай|горно-алтайск', adres, re.I) and 'край' not in adres.lower(): continue
    if inn not in have:
        c.execute('insert or ignore into predpriyatiya(inn, ogrn, nazvanie, nazvanie_polnoe, adres, gorod, okved_osn, istochniki_zapisi, ts) values(?,?,?,?,?,?,?,?,?)',
                  (inn, it.get('ogrn'), it.get('nazvanie'), last.get('fullName'), adres, it.get('city') or it.get('district'), last.get('okved') or it.get('okved'), 'girbo', TS))
        have.add(inn); n_new += 1
    else:
        c.execute("update predpriyatiya set ogrn=coalesce(nullif(ogrn,''),?), nazvanie_polnoe=coalesce(nullif(nazvanie_polnoe,''),?), adres=coalesce(nullif(adres,''),?), okved_osn=coalesce(nullif(okved_osn,''),?), istochniki_zapisi=case when instr(coalesce(istochniki_zapisi,''),'girbo')>0 then istochniki_zapisi else coalesce(istochniki_zapisi,'')||'|girbo' end where inn=?",
                  (it.get('ogrn'), last.get('fullName'), adres, last.get('okved') or it.get('okved'), inn))
    for pr in d['periods']:
        v = pr.get('v2110'); pb = pr.get('p2400'); nal = pr.get('n2410')
        if v is None and pb is None: continue
        c.execute('insert or replace into finansy values(?,?,?,?,?,?,?,?)', (inn, 'girbo', str(pr.get('period')), v * 1000 if v is not None else None, pb * 1000 if pb is not None else None, abs(nal) * 1000 if nal is not None else None, None, TS))
        n_fin += 1
c.commit()
print('этап 3: новых ИНН', n_new, 'строк финансов', n_fin, '| predpriyatiya всего', c.execute('select count(*) from predpriyatiya').fetchone()[0], flush=True)
c.close()
ost = len(spisok) - len(done_ids) - schet['ok'] - schet['pusto']
if spisok_polon and ost <= 0:
    print('ГОТОВО')
