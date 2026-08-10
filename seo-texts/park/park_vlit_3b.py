# -*- coding: utf-8 -*-
"""Приём: park_ingest_3b (факты ЕИС), EIS-ZAKAZCHIKI (теперь с ИНН), LPR-NAYDENY (люди).
Поправка владельца учтена: МКС = МОДУЛЬНАЯ, ПКС = ПЕРЕДВИЖНАЯ, ярлык «МКС / передвижная»
разводим по признакам, а не переносим склейку в базу."""
import sqlite3, json, re, os, time, importlib.util
D = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('pb', os.path.join(D, 'park_build.py'))
pb = importlib.util.module_from_spec(spec); spec.loader.exec_module(pb)
p = sqlite3.connect(os.path.join(D, 'park.db')); cur = p.cursor()
INN = re.compile(r'^\d{10}$|^\d{12}$')
_PKS = re.compile(r'(?i)\bXATS|\bXAS\b|XAHS|\bPDS\b|\bDCA-|\bDCW-|ЗИФ-?ПВ|ПКСД|'
                  r'передвижн|на\s+шасси|на\s+прицеп|дизельн\w+\s+компрессорн|гар№|г/н\s*\d')
_MKS = re.compile(r'(?i)модульн|блочно-модульн|блок-контейнер|контейнерн\w+\s+исполнен|БМКС|'
                  r'компрессорн\w+\s+(станци\w+\s+)?под\s+ключ|компрессорн\w+\s+в\s+модуле')

def tochnyy_tip(yarlyk, tekst):
    """Ярлык 3-й «МКС / передвижная» — склейка двух типов. Разводим по тексту."""
    y = (yarlyk or '').strip()
    if 'МКС' in y or 'передвиж' in y.lower():
        t = tekst or ''
        if _MKS.search(t): return 'МКС'
        if _PKS.search(t): return 'ПКС'
        return 'ПКС'          # умолчание: в этой выгрузке преобладают дизельные на шасси
    return y

def ssyl(s):
    return [u.strip().rstrip(']') for u in re.split(r'\s*\|\s*', s or '') if u.strip().startswith('http')]

def zhur(chto, vs, pr, ot, pri):
    cur.execute('insert into zhurnal_vlivaniya values (?,?,?,?,?,?)',
                (time.strftime('%Y-%m-%d %H:%M:%S'), chto, vs, pr, ot,
                 json.dumps(pri, ensure_ascii=False)))
    print('  %-44s всего=%-6s принято=%-6s брак=%-5s %s' % (chto[:44], vs, pr, ot, pri))

# ---- 1. факты ЕИС от 3-й ----------------------------------------------------
vs = pr = ot = 0; pri = {}
for ln in open(os.path.join(D, 'park_ingest_3b.jsonl'), encoding='utf-8'):
    if not ln.strip(): continue
    vs += 1; r = json.loads(ln)
    inn = (r.get('inn') or '').strip(); urls = ssyl(r.get('istochniki'))
    if not INN.match(inn) or not urls:
        ot += 1; pri['нет ИНН или ссылки'] = pri.get('нет ИНН или ссылки', 0) + 1; continue
    nz = (r.get('nazvanie_zakupki') or '')
    tip = tochnyy_tip(r.get('vid'), nz)
    dedup = '|'.join([inn, tip, '', '', '', urls[0]])
    cur.execute('insert or ignore into fakt(inn,nazvanie,tip,sostoyanie,marka,model,napisanie,'
                'zavodskoy_nomer,sreda,summa,data_fakta,srok_do,sila,chem_rang,rang_mashiny,'
                'chto_naydeno,pochemu,uverennost,kto,karantin,dedup,ts) '
                'values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (inn, (r.get('organizaciya') or '')[:200], tip, 'неясно', '', '', '', '', '',
                 '', '', '', 5, 'C: ветка %s, принцип %s' % (r.get('vetka'), r.get('princip')),
                 r.get('klass_ceny'), nz[:500],
                 'закупка ЕИС, найдена запросом «%s»' % (r.get('zapros_kotorym_nashli') or ''),
                 'srednyaya', 'park_ingest_3b.jsonl (3-я)', '', dedup,
                 time.strftime('%Y-%m-%d %H:%M:%S')))
    fid = cur.execute('select id from fakt where dedup=?', (dedup,)).fetchone()[0]
    for u in urls[:20]:
        raz = pb.razbor_url(u)
        if raz:
            cur.execute('insert or ignore into fakt_ssylka(fakt_id,url,domen,istochnik,etap,'
                        'pervoistochnik,data_nablyudeniya,fayl) values (?,?,?,?,?,?,?,?)',
                        (fid, u, raz[0], raz[1], '', raz[2], '', ''))
    pr += 1
zhur('park_ingest_3b.jsonl (факты ЕИС 3-й)', vs, pr, ot, pri); p.commit()

# ---- 2. ЕИС-заказчики: теперь С ИНН -----------------------------------------
vs = pr = ot = 0; pri = {}
for ln in open(os.path.join(D, 'PARK-EIS-ZAKAZCHIKI-3S.jsonl'), encoding='utf-8'):
    if not ln.strip(): continue
    vs += 1; r = json.loads(ln)
    inn = (r.get('inn') or '').strip(); urls = ssyl(r.get('istochniki')) or \
        ssyl(r.get('zakazchik_kartochka'))
    if not INN.match(inn) or not urls:
        ot += 1; pri['нет ИНН или ссылки'] = pri.get('нет ИНН или ссылки', 0) + 1; continue
    predmet = (r.get('predmet') or '')
    tip = tochnyy_tip(pb.tip_po_tekstu(predmet) or (r.get('slova') or ''), predmet)
    dedup = '|'.join([inn, tip, '', '', '', (r.get('nomer') or urls[0])])
    cur.execute('insert or ignore into fakt(inn,nazvanie,tip,sostoyanie,marka,model,napisanie,'
                'zavodskoy_nomer,sreda,summa,data_fakta,srok_do,sila,chem_rang,chto_naydeno,'
                'pochemu,uverennost,kto,karantin,dedup,ts) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (inn, (r.get('zakazchik') or '')[:200], tip, 'неясно', '', '', '', '', '', '',
                 '', '', 5, 'закупка ЕИС; слово подтверждено текстом: %s' %
                 r.get('slovo_podtverzhdeno_tekstom'), predmet[:500],
                 'ИНН: %s' % (r.get('inn_otkuda') or ''), 'srednyaya',
                 'PARK-EIS-ZAKAZCHIKI-3S.jsonl (3-я, с ИНН)', '', dedup,
                 time.strftime('%Y-%m-%d %H:%M:%S')))
    fid = cur.execute('select id from fakt where dedup=?', (dedup,)).fetchone()[0]
    for u in urls[:10]:
        raz = pb.razbor_url(u)
        if raz:
            cur.execute('insert or ignore into fakt_ssylka(fakt_id,url,domen,istochnik,etap,'
                        'pervoistochnik,data_nablyudeniya,fayl) values (?,?,?,?,?,?,?,?)',
                        (fid, u, raz[0], raz[1], '', raz[2], '', ''))
    pr += 1
zhur('PARK-EIS-ZAKAZCHIKI-3S.jsonl (починена, с ИНН)', vs, pr, ot, pri); p.commit()

# ---- 3. ЛПР от 3-й: люди с ролью и ссылкой ----------------------------------
vs = pr = ot = 0; pri = {}
for ln in open(os.path.join(D, 'PARK-LPR-NAYDENY-3S.jsonl'), encoding='utf-8'):
    if not ln.strip(): continue
    r = json.loads(ln); inn = (r.get('inn') or '').strip()
    for ch in (r.get('lyudi') or []):
        vs += 1
        u = (ch.get('ssylka') or '').strip(); raz = pb.razbor_url(u)
        fio = (ch.get('fio') or '').strip()
        if not INN.match(inn) or not raz or not fio:
            ot += 1; pri['нет ИНН, ссылки или ФИО'] = pri.get('нет ИНН, ссылки или ФИО', 0) + 1; continue
        cur.execute('insert or ignore into contact_source(inn,vid,znachenie,person,dolzhnost,'
                    'istochnik,source_url,domen,pervoistochnik,data_nablyudeniya,quote,kto) '
                    'values (?,?,?,?,?,?,?,?,?,?,?,?)',
                    (inn, 'chelovek', fio.lower(), fio, (ch.get('dolzhnost') or '').strip(),
                     raz[1], u, raz[0], raz[2], '', (ch.get('citata') or '')[:300],
                     'PARK-LPR-NAYDENY-3S.jsonl (3-я)'))
        pr += 1
zhur('PARK-LPR-NAYDENY-3S.jsonl (ЛПР 3-й)', vs, pr, ot, pri); p.commit()

q = lambda s: cur.execute(s).fetchone()[0]
print()
print('=== ИТОГО ===')
for t, s in (('фактов', "select count(*) from fakt"), ('ИНН с фактом', "select count(distinct inn) from fakt"),
             ('ИНН силы 1', "select count(distinct inn) from fakt where sila=1"),
             ('ссылок', "select count(*) from fakt_ssylka"),
             ('наблюдений контакта', "select count(*) from contact_source"),
             ('ИНН с ЧЕЛОВЕКОМ', "select count(distinct inn) from contact_source where vid='chelovek'")):
    print('  %-24s %s' % (t, q(s)))
print('--- МКС и ПКС теперь раздельно ---')
for r in cur.execute("select tip,count(*),count(distinct inn) from fakt where tip in ('МКС','ПКС') group by 1"):
    print('  %-6s строк=%-6s ИНН=%s' % r)
p.close()
