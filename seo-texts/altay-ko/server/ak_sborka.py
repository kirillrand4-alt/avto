# -*- coding: utf-8 -*-
"""Фаза 5. Сборка выдачи из AK-BAZA.sqlite: три CSV (;-разделитель, utf-8-sig) + сводка, всё на дроп.
  AK-PREDPRIYATIYA.csv           одна строка на юрлицо края с классом (доказано / косвенно / кандидат) и рангом
  AK-FINANSY.csv                 все финансовые строки по этим юрлицам, по источникам (ГИР БО, ФНС, checko, обзвон)
  AK-KARTOCHKI-DOKAZATELSTV.csv  одна строка на факт: вид, тип машины, ссылка на первоисточник, цитата
argv: [FULL] - включить и «не наше» / «не оценено» в предприятия (для контроля)."""
import os, sys, re, csv, json, sqlite3, urllib.request, time, collections
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
AK = r'C:\sender\_ops\ak'; DB = os.path.join(AK, 'AK-BAZA.sqlite'); OUT = os.path.join(AK, 'vydacha'); os.makedirs(OUT, exist_ok=True)
FULL = 'FULL' in sys.argv
c = sqlite3.connect(f'file:{DB}?mode=ro', uri=True); c.row_factory = sqlite3.Row
SLAB = {'холодильный компрессор', 'ОПО (иное)'}
# ---- факты по ИНН
fakty = collections.defaultdict(list)
for r in c.execute('select * from fakty'):
    fakty[r['inn']].append(dict(r))
def klass_po_faktam(fs):
    silnye = [f for f in fs if (f['sila'] or 0) >= 3 and f['tip'] not in SLAB and f['vid_fakta'] not in ('расход газа ЕИС',)]
    if silnye: return 'доказано'
    if fs: return 'доказано (слабо)'
    return ''
# ---- финансы
fin = collections.defaultdict(list)
for r in c.execute('select * from finansy'):
    fin[r['inn']].append(dict(r))
PRIOR = ['girbo', 'fns-revexp', 'checko', 'checko(requisites)', 'checko(finansy)', 'checko(park-2s)', 'obzvon', 'enrich.companies', 'master']
def luchshie_finansy(inn):
    rows = fin.get(inn, [])
    vyr = None
    for src in PRIOR:
        cand = [x for x in rows if x['istochnik'] == src and (x['vyruchka_rub'] or 0) > 0]
        if cand:
            cand.sort(key=lambda x: x['fin_god'] or '', reverse=True); vyr = cand[0]; break
    prib = None
    for src in ['girbo', 'fns-revexp', 'checko', 'checko(requisites)', 'checko(finansy)', 'obzvon']:
        cand = [x for x in rows if x['istochnik'] == src and x['pribyl_rub'] is not None]
        if cand:
            cand.sort(key=lambda x: x['fin_god'] or '', reverse=True); prib = cand[0]; break
    nal = [x for x in rows if x['istochnik'] == 'fns-paytax' and x['nalogi_rub'] is not None]
    nal.sort(key=lambda x: x['fin_god'] or '', reverse=True)
    ssch = [x for x in rows if x['istochnik'] == 'fns-sshr' and x['ssch']]
    ssch.sort(key=lambda x: x['fin_god'] or '', reverse=True)
    return vyr, prib, (nal[0] if nal else None), (ssch[0] if ssch else None)
KLASS_ORDER = {'доказано': 0, 'косвенно': 1, 'доказано (слабо)': 2, 'кандидат': 3, 'кандидат (линзы разошлись)': 4, 'кандидат (слабый)': 5, 'не оценено': 6, 'без вердикта': 6, 'не наше': 7}
rows_out = []
for r in c.execute("select * from predpriyatiya where inn like '22%' or adres like '%Алтайский край%'"):
    inn = r['inn']; fs = fakty.get(inn, [])
    kl = klass_po_faktam(fs) or (r['klass'] or 'не оценено')
    if not FULL and kl in ('не наше', 'не оценено', 'без вердикта'): continue
    if r['status_egrul'] and re.search(r'LIQUIDAT|ликвидир|прекрат', r['status_egrul'], re.I) and not fs: continue
    vyr, prib, nal, ssch = luchshie_finansy(inn)
    vidy = collections.Counter(f['vid_fakta'] for f in fs); tipy = collections.Counter(f['tip'] for f in fs if f['tip'])
    marki = sorted({f['marka_model'] for f in fs if f['marka_model']})[:5]
    sroki = sorted({f['srok_do'] for f in fs if f['srok_do']})
    ist = sorted({f['istochnik'] for f in fs})
    rows_out.append({
        'inn': inn, 'ogrn': r['ogrn'] or '', 'nazvanie': r['nazvanie'] or r['nazvanie_polnoe'] or '', 'nazvanie_polnoe': r['nazvanie_polnoe'] or '', 'status_egrul': r['status_egrul'] or '',
        'gorod': r['gorod'] or '', 'adres': r['adres'] or '', 'okved_osn': r['okved_osn'] or '', 'okved_vse': (r['okved_vse'] or '')[:400],
        'klass': kl, 'uverennost': r['uverennost'] if kl.startswith('косвенно') or kl.startswith('кандидат') else (100 if kl == 'доказано' else 60 if kl.startswith('доказано') else ''),
        'tehprocess': (r['tehprocess'] or '') if not fs else ('; '.join(f'{k} x{v}' for k, v in vidy.most_common(6))),
        'tip_mashin': (r['tip_mashin'] or '') if not fs else ', '.join(f'{k} x{v}' for k, v in tipy.most_common(6)),
        'faktov_pryamyh': len(fs), 'istochnikov': len(ist), 'istochniki_faktov': ' | '.join(ist), 'marki': ' | '.join(marki), 'srok_epb_min': sroki[0] if sroki else '',
        'vyruchka_rub': int(vyr['vyruchka_rub']) if vyr else '', 'fin_god': (vyr['fin_god'] if vyr else ''), 'fin_istochnik': (vyr['istochnik'] if vyr else ''),
        'pribyl_rub': int(prib['pribyl_rub']) if prib else '', 'nalogi_rub': int(nal['nalogi_rub']) if nal else '', 'nalogi_god': nal['fin_god'] if nal else '',
        'ssch': (ssch['ssch'] if ssch else (r['ssch'] or '')), 'sayt': r['sayt'] or '', 'rukovoditel': r['rukovoditel'] or '', 'istochniki_zapisi': r['istochniki_zapisi'] or '',
    })
rows_out.sort(key=lambda x: (KLASS_ORDER.get(x['klass'], 9), -(x['vyruchka_rub'] or 0), -(x['faktov_pryamyh'] or 0)))
for i, x in enumerate(rows_out, 1): x['rang'] = i
kol = ['rang', 'inn', 'ogrn', 'nazvanie', 'nazvanie_polnoe', 'klass', 'uverennost', 'tehprocess', 'tip_mashin', 'faktov_pryamyh', 'istochnikov', 'istochniki_faktov', 'marki', 'srok_epb_min',
       'vyruchka_rub', 'fin_god', 'fin_istochnik', 'pribyl_rub', 'nalogi_rub', 'nalogi_god', 'ssch', 'okved_osn', 'okved_vse', 'gorod', 'adres', 'status_egrul', 'sayt', 'rukovoditel', 'istochniki_zapisi']
def pisat(name, kol, rows):
    p = os.path.join(OUT, name)
    with open(p, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=kol, delimiter=';', extrasaction='ignore'); w.writeheader(); w.writerows(rows)
    return p
p1 = pisat('AK-PREDPRIYATIYA.csv', kol, rows_out)
inns = {x['inn'] for x in rows_out}
fin_rows = []
for inn in inns:
    for x in fin.get(inn, []):
        fin_rows.append({'inn': inn, 'istochnik': x['istochnik'], 'fin_god': x['fin_god'], 'vyruchka_rub': x['vyruchka_rub'], 'pribyl_rub': x['pribyl_rub'], 'nalogi_rub': x['nalogi_rub'], 'ssch': x['ssch']})
fin_rows.sort(key=lambda x: (x['inn'], x['istochnik'], x['fin_god'] or ''))
p2 = pisat('AK-FINANSY.csv', ['inn', 'istochnik', 'fin_god', 'vyruchka_rub', 'pribyl_rub', 'nalogi_rub', 'ssch'], fin_rows)
kart = []
naz = {x['inn']: x['nazvanie'] for x in rows_out}
for inn in inns:
    for f in fakty.get(inn, []):
        kart.append({'inn': inn, 'predpriyatie': f['predpriyatie'] or naz.get(inn, ''), 'vid_fakta': f['vid_fakta'], 'tip': f['tip'], 'marka_model': f['marka_model'] or '', 'sreda': f['sreda'] or '', 'data': f['data'] or '',
                     'srok_do': f['srok_do'] or '', 'status_sroka': f['status_sroka'] or '', 'sila': f['sila'], 'istochnik': f['istochnik'], 'ssylka': f['ssylka'], 'citata': (f['citata'] or '').replace('\n', ' ')[:600], 'kto_sobral': f['kto_sobral'], 'ts': f['ts']})
kart.sort(key=lambda x: (x['inn'], -(x['sila'] or 0)))
p3 = pisat('AK-KARTOCHKI-DOKAZATELSTV.csv', ['inn', 'predpriyatie', 'vid_fakta', 'tip', 'marka_model', 'sreda', 'data', 'srok_do', 'status_sroka', 'sila', 'istochnik', 'ssylka', 'citata', 'kto_sobral', 'ts'], kart)
svod = {'predpriyatiy': len(rows_out), 'po_klassam': dict(collections.Counter(x['klass'] for x in rows_out)), 's_vyruchkoy': sum(1 for x in rows_out if x['vyruchka_rub']), 's_nalogami': sum(1 for x in rows_out if x['nalogi_rub']),
        's_ssch': sum(1 for x in rows_out if x['ssch']), 'kartochek': len(kart), 'inn_s_kartochkoy': len({k['inn'] for k in kart}), 'kartochek_po_vidu': dict(collections.Counter(k['vid_fakta'] for k in kart)),
        'istochniki_kartochek': dict(collections.Counter(k['istochnik'] for k in kart)), 'ts': time.strftime('%Y-%m-%d %H:%M')}
json.dump(svod, open(os.path.join(OUT, 'AK-SVODKA.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(json.dumps(svod, ensure_ascii=False, indent=1))
for p in (p1, p2, p3, os.path.join(OUT, 'AK-SVODKA.json')):
    data = open(p, 'rb').read()
    req = urllib.request.Request(os.environ['DROP_URL'].rstrip('/') + '/' + os.path.basename(p), data=data, method='PUT', headers={'X-Drop-Token': os.environ['DROP_TOKEN'], 'Content-Type': 'application/octet-stream'})
    r = urllib.request.urlopen(req, timeout=600); print(os.path.basename(p), r.status, len(data) // 1024, 'КБ')
