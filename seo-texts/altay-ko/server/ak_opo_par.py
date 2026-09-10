# -*- coding: utf-8 -*-
"""Реестр ОПО по ИНН, в несколько потоков через пул socks5.
Последовательный ak_opo.py прошёл 169 предприятий - только тех, у кого уже был факт. Между тем
«Площадка компрессорной станции» в перечне ОПО сама по себе доказательство, поэтому спрашиваем
всех производственных юрлиц края, крупные первыми. Каждый поток держит свой прокси и свою сессию.
Резюм по ИНН в общем opo-po-inn.jsonl. argv: [бюджет_сек] [потоков] [OBRATNO|SEREDINA] [TEST]."""
import os, re, sys, json, time, random, sqlite3, threading, itertools, warnings
import concurrent.futures as cf
warnings.filterwarnings('ignore')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
AK = r'C:\sender\_ops\ak'; DB = os.path.join(AK, 'AK-BAZA.sqlite'); sys.path.insert(0, AK)
import requests
requests.packages.urllib3.disable_warnings()
import park_opo_po_inn as O

BUDGET = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 1300
POTOKOV = min(4, int(sys.argv[2])) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 3  # больше четырёх реестр не держит
TEST = 'TEST' in sys.argv
T0 = time.time(); TS = time.strftime('%Y-%m-%d %H:%M')
F = os.path.join(AK, 'opo-po-inn.jsonl')

PR = [l.strip() for l in open(r'C:\sender\dolphin-proxies.txt', encoding='utf-8') if l.strip()]
random.shuffle(PR)
_mest = threading.local(); _zamok_pr = threading.Lock(); _sled = itertools.count()
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'

def _sess():
    if not hasattr(_mest, 's'):
        with _zamok_pr: _mest.pr = PR[next(_sled) % len(PR)] if PR else None
        s = requests.Session(); s.headers.update({'User-Agent': UA, 'Accept-Language': 'ru'}); s.verify = False
        if _mest.pr: s.proxies = {'http': 'socks5h://' + _mest.pr, 'https': 'socks5h://' + _mest.pr}
        _mest.s = s
    return _mest.s

def _smena():
    with _zamok_pr: _mest.pr = PR[next(_sled) % len(PR)] if PR else None
    if hasattr(_mest, 's') and _mest.pr:
        _mest.s.proxies = {'http': 'socks5h://' + _mest.pr, 'https': 'socks5h://' + _mest.pr}

def _vzyat(url, popytok=3):
    for i in range(popytok):
        try:
            r = _sess().get(url, timeout=60)
            if r.status_code == 200 and len(r.text) > 400: return r.text
            if r.status_code in (403, 429, 503): _smena()
        except Exception as e:
            _smena()
            if i == popytok - 1: return f'__ОШИБКА__ {type(e).__name__}: {str(e)[:70]}'
        time.sleep(1.0 * (i + 1))
    return '__ОШИБКА__ пустой ответ реестра'
O._vzyat = _vzyat
O.PAUZA = 0.0

c = sqlite3.connect(DB, timeout=180)
CAND = re.compile(r'^(0[1-9]|1\d|2\d|3[0-9]|4[1-3]|45\.2|49|52|71\.12|71\.2|72|77\.3|86\.1)')
vyr = {r[0]: (r[1] or 0) for r in c.execute('select inn, max(vyruchka_rub) from finansy group by 1')}
kand = [r[0] for r in c.execute("select inn, okved_osn from predpriyatiya where (inn like '22%' or adres like '%Алтайский край%') and (status_egrul is null or status_egrul not like '%LIQUID%')") if CAND.match(r[1] or '')]
c.close()
kand.sort(key=lambda i: -vyr.get(i, 0))
gotovo = set()
if os.path.exists(F):
    for l in open(F, encoding='utf-8', errors='replace'):
        try:
            d = json.loads(l)
            if not d.get('err'): gotovo.add(d['inn'])
        except Exception: pass
ochered = [i for i in kand if i not in gotovo]
if 'OBRATNO' in sys.argv: ochered = ochered[::-1]
if 'SEREDINA' in sys.argv: ochered = ochered[len(ochered) // 2:] + ochered[:len(ochered) // 2]
if TEST: ochered = ochered[:6]; POTOKOV = 3
print(f'производственных ИНН {len(kand)}, готово {len(gotovo)}, в очереди {len(ochered)}, потоков {POTOKOV}', flush=True)


# ---- проверка живости реестра. Когда monitor-pb молчит, парсер отдаёт пустой список БЕЗ ошибки,
# и прогон записывает «ничего нет» для непроверенных предприятий - хуже, чем не работать вовсе.
# Поэтому сначала спрашиваем предприятия, у которых записи заведомо есть.
def _reestr_zhiv():
    import sqlite3 as _s
    _c = _s.connect(f'file:{DB}?mode=ro', uri=True, timeout=60)
    _k = [r[0] for r in _c.execute("select inn from fakty where vid_fakta='ОПО' limit 3")]
    _c.close()
    for _inn in _k:
        try:
            _r = O.po_inn(_inn) if 'O' == 'O' else O.po_inn(_inn, max_stranic=2, tolko_tu=True)
            if isinstance(_r, tuple): _r = _r[0]
            if _r: return True, _inn
        except Exception:
            pass
    return False, ','.join(_k)
_zhiv, _kto = _reestr_zhiv()
if not _zhiv:
    print('РЕЕСТР МОЛЧИТ: контрольные ИНН', _kto, 'не дали ни одной записи - выходим, чтобы не записать ложные пустышки', flush=True)
    sys.exit(2)
print('реестр живой, контроль прошёл на', _kto, flush=True)

zamok = threading.Lock(); f = open(F, 'a', encoding='utf-8')
sch = {'ok': 0, 'err': 0, 'obektov': 0}
def rabota(inn):
    if time.time() - T0 > BUDGET: return None
    try:
        ob = O.po_inn(inn, stranic=4, kart=10, stop_posle=8)
        if isinstance(ob, tuple): ob = ob[0]
        d = {'inn': inn, 'obekty': [{k: o.get(k) for k in ('naimenovanie_obekta', 'klass_opasnosti', 'reg_nomer', 'ssylka', 'citata', 'data', 'kanal')} for o in (ob or [])], 'err': ''}
    except Exception as e:
        d = {'inn': inn, 'obekty': [], 'err': repr(e)[:100]}
    with zamok:
        f.write(json.dumps(d, ensure_ascii=False) + '\n'); f.flush()
        sch['err' if d['err'] else 'ok'] += 1; sch['obektov'] += len(d['obekty'])
        n = sch['ok'] + sch['err']
        if n % 50 == 0: print(f'  ...{n} ИНН, объектов {sch["obektov"]}, сбоев {sch["err"]}, {int(time.time() - T0)} с', flush=True)
    time.sleep(0.4)
    return d

with cf.ThreadPoolExecutor(max_workers=POTOKOV) as ex:
    spisok = list(ex.map(rabota, ochered))
f.close()
print(f'заход: обработано {sch["ok"]}, сбоев {sch["err"]}, объектов ОПО {sch["obektov"]}', flush=True)

MASH = re.compile(r'компрессор|воздуходув|воздухоразделительн|азотн|кислородн|сжат\w+ воздух|пневм', re.I)
c = sqlite3.connect(DB, timeout=180); n_f = 0
for d in spisok:
    if not d: continue
    for o in d.get('obekty') or []:
        nm = o.get('naimenovanie_obekta') or ''
        if not o.get('ssylka') or not MASH.search(nm): continue
        cit = (nm + ' | класс ' + (o.get('klass_opasnosti') or '') + ' | рег.№ ' + (o.get('reg_nomer') or '') + ' | ' + (o.get('citata') or '')[:250])[:500]
        c.execute('''insert or ignore into fakty(inn,predpriyatie,vid_fakta,tip,marka_model,sreda,data,srok_do,status_sroka,sila,istochnik,ssylka,citata,kto_sobral,ts,klyuch) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                  (d['inn'], None, 'ОПО', 'компрессорная станция', o.get('reg_nomer') or '', '', o.get('data') or '', '', '', 5,
                   'monitor-pb.ru', o['ssylka'], cit, 'ak_opo', TS, f'{d["inn"]}|{o["ssylka"]}|компрессорная станция|{o.get("reg_nomer") or ""}|{cit[:80]}'))
        n_f += 1
c.commit()
print('объектов с нашими машинами:', n_f, '| ИНН с ОПО-фактом:', c.execute("select count(distinct inn) from fakty where vid_fakta='ОПО'").fetchone()[0], flush=True)
c.close()
ost = len(ochered) - sch['ok'] - sch['err']
print('осталось в очереди примерно', max(0, ost), flush=True)
if ost <= 0 and not TEST: print('ГОТОВО')
