# -*- coding: utf-8 -*-
"""Приём потоков соседей: EPB-ПОЛНЫЕ (2-я), park_ingest_3 + контакты + ЕИС (3-я).
Правило владельца: у факта и контакта ссылка обязательна; ссылок несколько — строк несколько."""
import sqlite3, csv, json, re, os, time, importlib.util
D = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('pb', os.path.join(D, 'park_build.py'))
pb = importlib.util.module_from_spec(spec); spec.loader.exec_module(pb)
p = sqlite3.connect(os.path.join(D, 'park.db')); cur = p.cursor()
INN = re.compile(r'^\d{10}$|^\d{12}$')

def zhur(chto, vsego, prin, otbr, prich):
    cur.execute('insert into zhurnal_vlivaniya values (?,?,?,?,?,?)',
                (time.strftime('%Y-%m-%d %H:%M:%S'), chto, vsego, prin, otbr,
                 json.dumps(prich, ensure_ascii=False)))
    print('  %-46s всего=%-7s принято=%-7s брак=%-6s %s' % (chto[:46], vsego, prin, otbr, prich))

def ssylki_iz(s):
    return [u.strip().rstrip(']') for u in re.split(r'\s*\|\s*', s or '') if u.strip().startswith('http')]

# ---------- 1. ЭПБ ПОЛНЫЕ (без центробежного фильтра) --------------------------
vs = pr = ot = 0; pri = {}
for r in csv.DictReader(open(os.path.join(D, 'PARK-FAKTY-2S-EPB-POLNYE.csv'),
                             encoding='utf-8-sig'), delimiter=';'):
    vs += 1
    inn = (r.get('inn') or '').strip(); url = (r.get('ssylka') or '').strip()
    raz = pb.razbor_url(url)
    if not INN.match(inn) or not raz:
        ot += 1; pri['ИНН или ссылка негодны'] = pri.get('ИНН или ссылка негодны', 0) + 1; continue
    domen, ist, pi = raz
    tip = (r.get('tip') or '').strip(); mm = (r.get('marka_model') or '').strip()
    zav = (r.get('zavodskoy_nomer') or '').strip(); data = (r.get('data') or '').strip()
    srok = (r.get('srok_do') or '').strip()
    dedup = '|'.join([inn, tip, '', mm, zav, data]) if (mm or zav) else '|'.join([inn, tip, '', '', '', url])
    chem = 'надзорная запись: заключение ЭПБ'
    cur.execute('insert or ignore into fakt(inn,nazvanie,tip,sostoyanie,marka,model,napisanie,'
                'zavodskoy_nomer,sreda,summa,data_fakta,srok_do,sila,chem_rang,chto_naydeno,'
                'pochemu,uverennost,kto,karantin,dedup,ts) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (inn, (r.get('predpriyatie') or '').strip(), tip, 'эксплуатирует', '', mm, '',
                 zav, (r.get('sreda') or '').strip(), '', data, srok, 1, chem,
                 (r.get('citata') or '')[:500],
                 'ЭПБ полный корпус без центробежного фильтра; вывод: %s' % (r.get('vyvod') or '—'),
                 'vysokaya', 'PARK-FAKTY-2S-EPB-POLNYE.csv (2-я)', '', dedup,
                 time.strftime('%Y-%m-%d %H:%M:%S')))
    fid = cur.execute('select id from fakt where dedup=?', (dedup,)).fetchone()[0]
    cur.execute('insert or ignore into fakt_ssylka(fakt_id,url,domen,istochnik,etap,pervoistochnik,'
                'data_nablyudeniya,fayl) values (?,?,?,?,?,?,?,?)',
                (fid, url, domen, 'реестр ЭПБ (Монитор ПБ)', '', 1, data,
                 (r.get('nomer_zaklucheniya') or '')))
    pr += 1
zhur('PARK-FAKTY-2S-EPB-POLNYE.csv', vs, pr, ot, pri); p.commit()

# ---------- 2. поток 3-й сессии ------------------------------------------------
vs = pr = ot = 0; pri = {}
for ln in open(os.path.join(D, 'park_ingest_3.jsonl'), encoding='utf-8'):
    if not ln.strip(): continue
    vs += 1; r = json.loads(ln)
    inn = (r.get('inn') or '').strip()
    urls = ssylki_iz(r.get('istochniki'))
    if not INN.match(inn) or not urls:
        ot += 1; pri['ИНН или ссылки нет'] = pri.get('ИНН или ссылки нет', 0) + 1; continue
    vid = (r.get('vid') or '').strip(); klyuch = (r.get('klyuch') or '').strip()
    dedup = '|'.join([inn, vid, '', klyuch, '', ''])
    cur.execute('insert or ignore into fakt(inn,nazvanie,tip,sostoyanie,marka,model,napisanie,'
                'zavodskoy_nomer,sreda,summa,data_fakta,srok_do,sila,chem_rang,rang_mashiny,'
                'chto_naydeno,pochemu,uverennost,kto,karantin,dedup,ts) '
                'values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (inn, '', vid, 'эксплуатирует', '', klyuch, (r.get('napisanie') or ''), '',
                 '', '', '', '', 2, 'C: серия %s, ветка %s, принцип %s' %
                 (klyuch, r.get('vetka'), r.get('princip')), r.get('klass_ceny'),
                 (r.get('citata') or '')[:500],
                 'поток 3-й сессии: серия найдена в %s документах, ИНН из %s' %
                 (r.get('istochnikov'), r.get('inn_otkuda')), 'srednyaya',
                 'park_ingest_3.jsonl (3-я)', '', dedup, time.strftime('%Y-%m-%d %H:%M:%S')))
    fid = cur.execute('select id from fakt where dedup=?', (dedup,)).fetchone()[0]
    for u in urls[:40]:
        raz = pb.razbor_url(u)
        if not raz: continue
        d_, i_, pi_ = raz
        cur.execute('insert or ignore into fakt_ssylka(fakt_id,url,domen,istochnik,etap,'
                    'pervoistochnik,data_nablyudeniya,fayl) values (?,?,?,?,?,?,?,?)',
                    (fid, u, d_, i_, '', pi_, '', ''))
    pr += 1
zhur('park_ingest_3.jsonl (поток 3-й)', vs, pr, ot, pri); p.commit()

# ---------- 3. контакты 3-й ----------------------------------------------------
vs = pr = ot = 0; pri = {}
for ln in open(os.path.join(D, 'PARK-KONTAKTY-3S.jsonl'), encoding='utf-8'):
    if not ln.strip(): continue
    vs += 1; r = json.loads(ln)
    inn = (r.get('inn') or '').strip()
    urls = ssylki_iz(r.get('istochniki'))
    if not INN.match(inn) or not urls:
        ot += 1; pri['ИНН или ссылки нет'] = pri.get('ИНН или ссылки нет', 0) + 1; continue
    nom = re.sub(r'\D', '', str(r.get('nomer') or ''))
    vidn = (r.get('vid_nomera') or '')
    imena = [x.strip() for x in re.split(r'\s*\|\s*', r.get('imya') or '') if x.strip()]
    dolzh = [x.strip() for x in re.split(r'\s*\|\s*', r.get('dolzhnost') or '') if x.strip()]
    if 'почта' in vidn:
        vid, zn = 'email', str(r.get('napisanie') or '').lower().strip()
    else:
        vid, zn = 'telefon', nom[-10:] if len(nom) >= 10 else ''
    if not zn: ot += 1; continue
    for u in urls[:20]:
        raz = pb.razbor_url(u)
        if not raz: continue
        d_, i_, pi_ = raz
        cur.execute('insert or ignore into contact_source(inn,vid,znachenie,person,dolzhnost,'
                    'istochnik,source_url,domen,pervoistochnik,data_nablyudeniya,quote,kto) '
                    'values (?,?,?,?,?,?,?,?,?,?,?,?)',
                    (inn, vid, zn, imena[0] if imena else '', dolzh[0] if dolzh else '',
                     i_, u, d_, pi_, '', (r.get('mashina') or '')[:200],
                     'PARK-KONTAKTY-3S.jsonl (3-я)'))
    pr += 1
zhur('PARK-KONTAKTY-3S.jsonl (контакты 3-й)', vs, pr, ot, pri); p.commit()

# ---------- 4. ЕИС-заказчики: ИНН пуст -> карантин на резолв -------------------
vs = pr = 0
for ln in open(os.path.join(D, 'PARK-EIS-ZAKAZCHIKI-3S.jsonl'), encoding='utf-8'):
    if not ln.strip(): continue
    vs += 1; r = json.loads(ln)
    urls = ssylki_iz(r.get('istochniki'))
    cur.execute('insert or ignore into fakt_bez_inn(nazvanie,tip,sostoyanie,model,napisanie,'
                'chto_naydeno,url,domen,istochnik,data_fakta,kto,ts) values (?,?,?,?,?,?,?,?,?,?,?,?)',
                ((r.get('zakazchik') or '').strip(), pb.tip_po_tekstu(r.get('predmet')), '',
                 '', '', (r.get('predmet') or '')[:400], urls[0] if urls else '', '', 'ЕИС', '',
                 'PARK-EIS-ZAKAZCHIKI-3S.jsonl (3-я)', time.strftime('%Y-%m-%d %H:%M:%S')))
    pr += 1
zhur('PARK-EIS-ZAKAZCHIKI-3S.jsonl -> карантин (ИНН пуст у ВСЕХ)', vs, pr, 0,
     {'ИНН нет ни у одной строки': vs}); p.commit()
print()
q = lambda s: cur.execute(s).fetchone()[0]
print('=== ИТОГО ===')
for t, s in (('фактов', "select count(*) from fakt"), ('ИНН с фактом', "select count(distinct inn) from fakt"),
             ('ИНН силы 1', "select count(distinct inn) from fakt where sila=1"),
             ('ссылок-доказательств', "select count(*) from fakt_ssylka"),
             ('наблюдений контакта', "select count(*) from contact_source"),
             ('в карантине без ИНН', "select count(*) from fakt_bez_inn")):
    print('  %-24s %s' % (t, q(s)))
print('--- по типу, ИНН ---')
for r in cur.execute("select tip,count(*),count(distinct inn) from fakt where tip!='' "
                     "group by 1 order by 3 desc limit 14"):
    print('  %-30s строк=%-6s ИНН=%s' % r)
p.close()
