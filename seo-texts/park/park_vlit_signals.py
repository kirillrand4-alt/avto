# -*- coding: utf-8 -*-
"""Вливание сигналов боевой enrich.db в park.db по ВСЕЙ номенклатуре.
enrich.db читалась на сервере (mode=ro), сюда пришёл gzip-JSON."""
import sqlite3, json, gzip, re, time, os
D = os.path.dirname(os.path.abspath(__file__))
import importlib.util
spec = importlib.util.spec_from_file_location('pb', os.path.join(D, 'park_build.py'))
pb = importlib.util.module_from_spec(spec); spec.loader.exec_module(pb)

rows = json.loads(gzip.decompress(open(os.path.join(D, '_park_signals.json.gz'), 'rb').read()))
p = sqlite3.connect(os.path.join(D, 'park.db')); cur = p.cursor()

# новостной агрегатор Google News — ссылка ведёт на редирект, а не на документ
AGG = ('news.google.com', 'yandex.ru/news')

_VAK = re.compile(r'(?i)вакансия|hh\.ru|машинист|аппаратчик|слесар')
prin = otbr = 0
prichiny = {}
for r in rows:
    inn = (r.get('inn') or '').strip()
    if not re.fullmatch(r'\d{10}|\d{12}', inn):
        otbr += 1; prichiny['ИНН не 10/12'] = prichiny.get('ИНН не 10/12', 0) + 1; continue
    what = (r.get('what') or '').strip()
    url = (r.get('source_url') or '').strip()
    raz = pb.razbor_url(url)
    if not raz:
        otbr += 1; prichiny['ссылка не URL'] = prichiny.get('ссылка не URL', 0) + 1; continue
    domen, istochnik, pi = raz
    if any(a in domen for a in AGG):
        istochnik = 'новостной агрегатор (редирект)'; pi = 0
    tip = pb.tip_po_tekstu(what)
    if not tip:
        otbr += 1; prichiny['тип машины не определён'] = prichiny.get('тип машины не определён', 0) + 1; continue
    ev = (r.get('event_type') or '').lower()
    if pb._TO.search(what):
        sost, sila, chem = 'эксплуатирует', 2, 'закупка/работы по обслуживанию'
    elif _VAK.search(what) or 'вакан' in (r.get('source') or '').lower() or 'hh' in (r.get('source') or '').lower():
        sost, sila, chem = 'эксплуатирует', 4, 'профессия в вакансии'
    elif 'план' in ev or 'план' in what.lower():
        sost, sila, chem = 'планирует', 3, 'план закупки — намерение'
    elif re.search(r'(?i)поставк|приобрет|закупк|покупк|тендер на', what):
        sost, sila, chem = 'покупает машину', 5, 'закупка на покупку машины'
    else:
        sost, sila, chem = 'неясно', 6, 'упоминание в новости/сигнале'
    if pi == 0:
        sila = max(sila, 6)   # агрегатор сам по себе не подтверждает
    dedup = '|'.join([inn, tip, '', '', '', url])
    cur.execute('insert or ignore into fakt(inn,nazvanie,tip,sostoyanie,marka,model,napisanie,'
                'zavodskoy_nomer,sreda,summa,data_fakta,srok_do,sila,chem_rang,chto_naydeno,'
                'pochemu,uverennost,kto,karantin,dedup,ts) '
                'values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (inn, '', tip, sost, '', '', '', '', '', r.get('sum') or '',
                 (r.get('ts') or '')[:25], '', sila, chem, what,
                 'сигнал боевой базы: %s / %s' % (r.get('source'), ev), '',
                 'enrich.db/signals', '', dedup, time.strftime('%Y-%m-%d %H:%M:%S')))
    fid = cur.execute('select id from fakt where dedup=?', (dedup,)).fetchone()[0]
    cur.execute('insert or ignore into fakt_ssylka(fakt_id,url,domen,istochnik,etap,'
                'pervoistochnik,data_nablyudeniya,fayl) values (?,?,?,?,?,?,?,?)',
                (fid, url, domen, istochnik, '', pi, (r.get('ts') or '')[:25], ''))
    prin += 1

cur.execute('insert into zhurnal_vlivaniya values (?,?,?,?,?,?)',
            (time.strftime('%Y-%m-%d %H:%M:%S'), 'enrich.db/signals (вся номенклатура)',
             len(rows), prin, otbr, json.dumps(prichiny, ensure_ascii=False)))
p.commit()
print('всего=%s принято=%s брак=%s %s' % (len(rows), prin, otbr, prichiny))
print()
print('=== park.db ПОСЛЕ вливания ===')
for q, t in (("select count(*) from fakt", 'фактов'),
             ("select count(distinct inn) from fakt", 'ИНН с фактом'),
             ("select count(*) from fakt_ssylka", 'ссылок')):
    print('  %-22s %s' % (t, cur.execute(q).fetchone()[0]))
print('--- по типу машины ---')
for r in cur.execute("select case when tip='' then '(не установлен)' else tip end,"
                     "count(*),count(distinct inn) from fakt group by 1 order by 3 desc"):
    print('  %-26s строк=%-6s ИНН=%s' % r)
print('--- по силе ---')
for r in cur.execute('select sila,count(*),count(distinct inn) from fakt group by 1 order by 1'):
    print('  сила %s: строк=%-6s ИНН=%s' % r)
p.close()
