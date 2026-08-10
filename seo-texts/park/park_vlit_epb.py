# -*- coding: utf-8 -*-
"""Вливание корпуса ЭПБ 2-й сессии. Разрез согласован: 2-я разбирает, 1-я вливает."""
import sqlite3, csv, re, time, os, json, importlib.util
D = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('pb', os.path.join(D, 'park_build.py'))
pb = importlib.util.module_from_spec(spec); spec.loader.exec_module(pb)
p = sqlite3.connect(os.path.join(D, 'park.db')); cur = p.cursor()

vsego = prin = otbr = 0
prich = {}
f = open(os.path.join(D, 'PARK-FAKTY-2S-EPB.csv'), encoding='utf-8-sig')
for row in csv.DictReader(f, delimiter=';'):
    vsego += 1
    inn = (row.get('inn') or '').strip()
    if not re.fullmatch(r'\d{10}|\d{12}', inn):
        otbr += 1; prich['ИНН не 10/12'] = prich.get('ИНН не 10/12', 0) + 1; continue
    url = (row.get('ssylka') or '').strip()
    raz = pb.razbor_url(url)
    if not raz:
        otbr += 1; prich['нет ссылки-доказательства'] = prich.get('нет ссылки-доказательства', 0) + 1; continue
    domen, istochnik, pi = raz
    tip = (row.get('tip') or '').strip()
    # «узел X» — это составная часть, а не машина: тип оставляем, но помечаем
    uzel = tip.startswith('узел ')
    mm = (row.get('marka_model') or '').strip()
    zav = (row.get('zavodskoy_nomer') or '').strip()
    data = (row.get('data') or '').strip()
    srok = (row.get('srok_do') or '').strip()
    stat = (row.get('status_sroka') or '').strip()
    # ключ по канону: машина различается ЗАВОДСКИМ НОМЕРОМ
    dedup = '|'.join([inn, tip, '', mm, zav, data]) if (mm or zav) else \
            '|'.join([inn, tip, '', '', '', url])
    chem = 'надзорная запись: заключение ЭПБ'
    if stat == 'истёк':
        chem += '; СРОК ИСТЁК — ресурс выработан'
    cur.execute('insert or ignore into fakt(inn,nazvanie,tip,sostoyanie,marka,model,napisanie,'
                'zavodskoy_nomer,sreda,summa,data_fakta,srok_do,sila,chem_rang,chto_naydeno,'
                'pochemu,uverennost,kto,karantin,dedup,ts) '
                'values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (inn, (row.get('predpriyatie') or '').strip(), tip, 'эксплуатирует', '', mm, '',
                 zav, (row.get('sreda') or '').strip(), '', data, srok, 1, chem,
                 (row.get('citata') or '').strip()[:500],
                 'экспертиза промышленной безопасности; узел=%s; статус срока=%s' % (uzel, stat or '—'),
                 'vysokaya', 'PARK-FAKTY-2S-EPB.csv (2-я сессия)', '', dedup,
                 time.strftime('%Y-%m-%d %H:%M:%S')))
    fid = cur.execute('select id from fakt where dedup=?', (dedup,)).fetchone()[0]
    cur.execute('insert or ignore into fakt_ssylka(fakt_id,url,domen,istochnik,etap,'
                'pervoistochnik,data_nablyudeniya,fayl) values (?,?,?,?,?,?,?,?)',
                (fid, url, domen, 'реестр ЭПБ (Монитор ПБ)', '', 1, data,
                 (row.get('istochnik') or '').strip()))
    prin += 1

cur.execute('insert into zhurnal_vlivaniya values (?,?,?,?,?,?)',
            (time.strftime('%Y-%m-%d %H:%M:%S'), 'PARK-FAKTY-2S-EPB.csv (корпус ЭПБ 2-й)',
             vsego, prin, otbr, json.dumps(prich, ensure_ascii=False)))
p.commit()
print('ЭПБ: всего=%s принято=%s брак=%s %s' % (vsego, prin, otbr, prich))
print()
print('=== park.db ИТОГО ===')
for q, t in (("select count(*) from fakt", 'фактов'),
             ("select count(distinct inn) from fakt", 'ИНН с фактом'),
             ("select count(*) from fakt_ssylka", 'ссылок-доказательств'),
             ("select count(distinct inn) from fakt where sila<=3", 'ИНН с доказательством силы 1-3'),
             ("select count(*) from fakt where zavodskoy_nomer!=''", 'фактов с ЗАВОДСКИМ НОМЕРОМ'),
             ("select count(distinct inn) from fakt where srok_do!='' and chem_rang like '%ИСТЁК%'",
              'ИНН с ИСТЁКШИМ сроком ЭПБ')):
    print('  %-38s %s' % (t, cur.execute(q).fetchone()[0]))
print('--- по типу (ИНН) ---')
for r in cur.execute("select case when tip='' then '(не установлен)' else tip end,"
                     "count(*),count(distinct inn) from fakt group by 1 order by 3 desc limit 16"):
    print('  %-28s строк=%-6s ИНН=%s' % r)
print('--- по силе ---')
for r in cur.execute('select sila,count(*),count(distinct inn) from fakt group by 1 order by 1'):
    print('  сила %s: строк=%-6s ИНН=%s' % r)
p.close()
