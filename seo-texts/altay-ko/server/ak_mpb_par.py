# -*- coding: utf-8 -*-
"""Реестр ЭПБ по ИНН, в несколько потоков через пул socks5.
Последовательный этап B в ak_mpb.py прошёл 372 ИНН из 7 129 производственных - слишком медленно.
Реестр душит один адрес, поэтому каждый поток берёт СВОЙ прокси из пула и держит свою сессию:
нагрузка на реестр с одного адреса остаётся прежней, а суммарная скорость растёт кратно.
Очередь резюмируется по ИНН в том же mpb-po-inn.jsonl, что и последовательный проход,
поэтому оба могут идти одновременно и не переделывать чужое.
argv: [бюджет_сек] [потоков] [TEST]."""
import os, sys, re, json, time, random, sqlite3, threading, itertools, warnings
import concurrent.futures as cf
warnings.filterwarnings('ignore')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
AK = r'C:\sender\_ops\ak'; DB = os.path.join(AK, 'AK-BAZA.sqlite'); sys.path.insert(0, AK)
import requests
requests.packages.urllib3.disable_warnings()
import mpb_po_inn as M

BUDGET = int(sys.argv[1]) if len(sys.argv) > 1 else 1300
POTOKOV = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 6
TEST = 'TEST' in sys.argv
T0 = time.time(); TS = time.strftime('%Y-%m-%d %H:%M')
F_B = os.path.join(AK, 'mpb-po-inn.jsonl')

PR = [l.strip() for l in open(r'C:\sender\dolphin-proxies.txt', encoding='utf-8') if l.strip()]
random.shuffle(PR)
_mest = threading.local()
_zamok_pr = threading.Lock(); _sled = itertools.count()
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36', 'Accept-Language': 'ru'}

def _moya_sessiya():
    """Своя сессия и свой прокси на поток: реестр видит несколько разных клиентов, а не один частящий."""
    if not hasattr(_mest, 's'):
        with _zamok_pr:
            _mest.pr = PR[next(_sled) % len(PR)] if PR else None
        s = requests.Session(); s.headers.update(UA); s.verify = False
        if _mest.pr:
            s.proxies = {'http': 'socks5h://' + _mest.pr, 'https': 'socks5h://' + _mest.pr}
        _mest.s = s
    return _mest.s

def _smenit_proksi():
    with _zamok_pr:
        _mest.pr = PR[next(_sled) % len(PR)] if PR else None
    if hasattr(_mest, 's') and _mest.pr:
        _mest.s.proxies = {'http': 'socks5h://' + _mest.pr, 'https': 'socks5h://' + _mest.pr}

def _vzyat(url, popytok=3):
    for i in range(popytok):
        s = _moya_sessiya()
        try:
            r = s.get(url, timeout=60)
            if r.status_code == 200 and len(r.text) > 400: return r.text
            if r.status_code in (403, 429, 503): _smenit_proksi()
        except Exception as e:
            _smenit_proksi()
            if i == popytok - 1: return f'__ОШИБКА__ {type(e).__name__}: {str(e)[:70]}'
        time.sleep(1.0 * (i + 1))
    return '__ОШИБКА__ пустой ответ реестра'
M._vzyat = _vzyat
M.PAUZA = 0.0   # паузу держит сам поток, у каждого свой адрес

# ---- очередь: производственные ИНН края, крупные первыми
c = sqlite3.connect(DB, timeout=180)
CAND = re.compile(r'^(0[1-9]|1\d|2\d|3[0-9]|4[1-3]|45\.2|49|52|71\.12|71\.2|72|77\.3|86\.1)')
vyr = {r[0]: (r[1] or 0) for r in c.execute("select inn, max(vyruchka_rub) from finansy group by 1")}
kand = [r[0] for r in c.execute("select inn, okved_osn from predpriyatiya where (inn like '22%' or adres like '%Алтайский край%') and (status_egrul is null or status_egrul not like '%LIQUID%')") if CAND.match(r[1] or '')]
c.close()
kand.sort(key=lambda i: -vyr.get(i, 0))
gotovo = set()
if os.path.exists(F_B):
    for l in open(F_B, encoding='utf-8', errors='replace'):
        try:
            d = json.loads(l)
            if not d.get('err'): gotovo.add(d['inn'])
        except Exception: pass
ochered = [i for i in kand if i not in gotovo]
# OBRATNO: второй прогон идёт с хвоста очереди навстречу первому - два независимых захода
# не перепахивают одни и те же ИНН, пока не встретятся посередине.
if 'OBRATNO' in sys.argv: ochered = ochered[::-1]
# SEREDINA: третий прогон стартует с середины очереди - три захода расходятся по разным её частям
if 'SEREDINA' in sys.argv: ochered = ochered[len(ochered) // 2:] + ochered[:len(ochered) // 2]
if TEST: ochered = ochered[:6]; POTOKOV = 3
print(f'производственных ИНН {len(kand)}, готово {len(gotovo)}, в очереди {len(ochered)}, потоков {POTOKOV}', flush=True)

zamok_f = threading.Lock()
f = open(F_B, 'a', encoding='utf-8')
schet = {'ok': 0, 'err': 0, 'strok': 0}

def rabota(inn):
    if time.time() - T0 > BUDGET: return None
    try:
        rows, err = M.po_inn(inn, max_stranic=40, tolko_tu=True)
    except Exception as e:
        rows, err = [], repr(e)[:100]
    d = {'inn': inn, 'err': (err or '')[:80], 'n': len(rows),
         'stroki': [{k: r.get(k) for k in ('nomer', 'data', 'obekt', 'tip', 'ekspertnaya_org', 'ssylka', 'nashe_oborudovanie', 'centrobezhnoe', 'nasos', 'predpriyatie')} for r in rows]}
    with zamok_f:
        f.write(json.dumps(d, ensure_ascii=False) + '\n'); f.flush()
        schet['err' if err else 'ok'] += 1; schet['strok'] += len(rows)
        n = schet['ok'] + schet['err']
        if n % 50 == 0: print(f'  ...{n} ИНН, строк {schet["strok"]}, сбоев {schet["err"]}, {int(time.time() - T0)} с', flush=True)
    time.sleep(0.5)
    return d

with cf.ThreadPoolExecutor(max_workers=POTOKOV) as ex:
    spisok = list(ex.map(rabota, ochered))
f.close()
print(f'заход: обработано {schet["ok"]}, сбоев {schet["err"]}, строк реестра {schet["strok"]}', flush=True)

# ---- разбор в факты (тот же гейт, что в ak_mpb.py: только наши машины, без насосов)
MASH = re.compile(r'компрессор|воздуходув|нагнетател|турбокомпрессор|ресивер|воздухосборник|осушител|воздухоразделительн|\bВРУ\b|генератор\w*\s+(азота|кислорода)|азотн\w+\s+(станц|установ)|кислородн\w+\s+(станц|установ)|компрессорн', re.I)
NASOS = M.NASOS
VIDY = [('генератор кислорода', r'кислородн\w*\s*(станц|генератор|установ)|генератор\w*\s*кислород'), ('генератор азота', r'азотн\w*\s*(станц|генератор|установ)|генератор\w*\s*азот'),
        ('ВРУ', r'воздухоразделительн|\bВРУ\b'), ('нагнетатель', r'нагнетател'), ('воздуходувка', r'воздуходув|турбовоздуходув'), ('осушитель', r'осушител'),
        ('ресивер', r'ресивер|воздухосборник'), ('компрессорная станция', r'компрессорн\w+\s+(станц|установк|цех)'), ('компрессор', r'компрессор')]
VIDY = [(v, re.compile(r, re.I)) for v, r in VIDY]
def vid(s):
    for v, rx in VIDY:
        if rx.search(s or ''): return v
    return ''
c = sqlite3.connect(DB, timeout=180); n_f = 0
for d in spisok:
    if not d: continue
    for r in d['stroki']:
        ob = r.get('obekt') or ''
        if not MASH.search(ob) or NASOS.search(ob): continue
        tip = vid(ob)
        if not tip: continue
        kl = f'{d["inn"]}|{r.get("ssylka")}|{tip}||{ob[:80]}'
        c.execute('''insert or ignore into fakty(inn,predpriyatie,vid_fakta,tip,marka_model,sreda,data,srok_do,status_sroka,sila,istochnik,ssylka,citata,kto_sobral,ts,klyuch)
                     values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                  (d['inn'], r.get('predpriyatie'), 'ЭПБ', tip, '', M.sreda(ob) if hasattr(M, 'sreda') else '', r.get('data'), '', '', 5,
                   'monitor-pb.ru', r.get('ssylka'), (ob[:400] + ' | ' + (r.get('nomer') or '') + ' | ' + (r.get('ekspertnaya_org') or ''))[:500], 'ak_mpb', TS, kl))
        n_f += 1
c.commit()
print('строк-кандидатов', n_f, '| ИНН с ЭПБ всего:', c.execute("select count(distinct inn) from fakty where vid_fakta='ЭПБ'").fetchone()[0], flush=True)
c.close()
if not TEST and not [i for i in ochered if i not in gotovo and time.time() - T0 <= BUDGET]:
    pass
ost = len(ochered) - schet['ok'] - schet['err']
print('осталось в очереди примерно', max(0, ost), flush=True)
if ost <= 0 and not TEST: print('ГОТОВО')
