# -*- coding: utf-8 -*-
"""Выгрузка кандидатов для линз (фаза 3) на дроп: AK-kandidaty.jsonl. Одна строка = юрлицо края с полями для классификации.
argv: [ALL] - все действующие; по умолчанию только кандидаты по ОКВЭД и предприятия с фактами."""
import os, sys, re, json, sqlite3, urllib.request, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
AK = r'C:\sender\_ops\ak'; DB = os.path.join(AK, 'AK-BAZA.sqlite')
CAND = re.compile(r'^(0[1-9]|1\d|2\d|3[0-9]|4[1-3]|45\.2|49|52|71\.12|71\.2|72|77\.3|86\.1)')
c = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
fakty = {}
for inn, vid, tip, n in c.execute("select inn, vid_fakta, tip, count(*) from fakty group by 1,2,3"):
    fakty.setdefault(inn, []).append(f'{vid}:{tip}x{n}')
fin = {}
for inn, god, v, p, s in c.execute("select inn, fin_god, vyruchka_rub, pribyl_rub, ssch from finansy where istochnik='girbo' order by fin_god"):
    fin[inn] = {'god': god, 'vyruchka': v, 'pribyl': p}
for inn, god, v, p, s in c.execute("select inn, fin_god, vyruchka_rub, pribyl_rub, ssch from finansy where istochnik!='girbo' and vyruchka_rub>0"):
    fin.setdefault(inn, {'god': god, 'vyruchka': v, 'pribyl': p})
out = os.path.join(AK, 'AK-kandidaty.jsonl'); n = 0
with open(out, 'w', encoding='utf-8') as f:
    for r in c.execute("select inn, nazvanie, nazvanie_polnoe, status_egrul, gorod, adres, okved_osn, okved_vse, sayt, activity, ssch, sayt_fakty_json from predpriyatiya where inn like '22%' or adres like '%Алтайский край%'"):
        inn, naz, nazp, st, gor, adr, ok, okv, sayt, act, ssch, sfj = r
        if st and re.search(r'LIQUIDAT|ликвидир|прекрат|недейств', st, re.I) and inn not in fakty: continue
        if 'ALL' not in sys.argv and inn not in fakty and not CAND.match(ok or ''): continue
        sf = {}
        if sfj:
            try:
                d = json.loads(sfj); kc = d.get('разбор_КЦ') or {}
                sf = {'vozduh_tochno': (kc.get('воздух_точно') or [])[:5], 'vozduh_veroyatno': (kc.get('воздух_вероятно') or [])[:5], 'priznak_kc': kc.get('признак_КЦ'), 'produkciya': (d.get('продукция') or [])[:5], 'moshchnosti': (d.get('мощности') or [])[:3], 'citata': (d.get('цитата') or '')[:200]}
            except Exception: pass
        f.write(json.dumps({'inn': inn, 'nazvanie': naz or nazp, 'nazvanie_polnoe': nazp, 'status': st, 'gorod': gor, 'adres': adr, 'okved_osn': ok, 'okved_vse': okv, 'sayt': sayt, 'activity': act, 'ssch': ssch,
                            'fin': fin.get(inn), 'sayt_fakty': sf, 'fakty': fakty.get(inn, [])}, ensure_ascii=False) + '\n'); n += 1
print('выгружено', n)
data = open(out, 'rb').read()
req = urllib.request.Request(os.environ['DROP_URL'].rstrip('/') + '/AK-kandidaty.jsonl', data=data, method='PUT', headers={'X-Drop-Token': os.environ['DROP_TOKEN'], 'Content-Type': 'application/octet-stream'})
r = urllib.request.urlopen(req, timeout=600); print('на дроп:', r.status, len(data) // 1024, 'КБ')
