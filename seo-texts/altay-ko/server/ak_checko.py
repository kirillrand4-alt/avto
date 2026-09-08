# -*- coding: utf-8 -*-
"""Т1.3/Т4. checko.ru через пул socks5: карточка (сайт, выручка, прибыль, ССЧ, основной ОКВЭД, статус) + /activity (все ОКВЭД) + /contacts (сайт, телефоны, почты).
Очередь: ИНН с фактами -> кандидаты по ОКВЭД -> остальные. Резюм по ИНН в checko.jsonl. 4 потока, каждый на своём прокси. argv: [бюджет] [TEST]."""
import os, sys, re, json, time, sqlite3, threading, requests
from concurrent.futures import ThreadPoolExecutor
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
requests.packages.urllib3.disable_warnings()
AK = r'C:\sender\_ops\ak'; DB = os.path.join(AK, 'AK-BAZA.sqlite'); F = os.path.join(AK, 'checko.jsonl')
BUDGET = int(sys.argv[1]) if len(sys.argv) > 1 else 1400; TEST = 'TEST' in sys.argv
T0 = time.time(); TS = time.strftime('%Y-%m-%d %H:%M')
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36', 'Accept-Language': 'ru,en;q=0.8'}
PR = [l.strip() for l in open(r'C:\sender\dolphin-proxies.txt', encoding='utf-8') if l.strip()]
def prox(i): pr = PR[i % len(PR)]; pr = 'socks5h://' + pr if '://' not in pr else pr; return {'http': pr, 'https': pr}
CAND = re.compile(r'^(0[1-9]|1\d|2\d|3[0-9]|4[1-3]|45\.2|49|52|71\.12|71\.2|72|77\.3|86\.1)')
def tekst(h):
    h = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', h)
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' | ', h))
SAYT = re.compile(r'(?:Сайт|Веб-сайт)[^a-zA-Z0-9]{0,25}((?:https?://)?[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*\.[a-zA-Z]{2,6})')
TEL = re.compile(r'\+7[\s(]?\d{3}[\s)]?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}')
POCHTA = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,6}')
CHUZHIE = re.compile(r'@checko\.|noreply|support@|example', re.I)
def chislo(s):
    m = re.search(r'(-?[\d\s]+(?:[.,]\d+)?)\s*(млрд|млн|тыс)?', s or '')
    if not m: return None
    v = float(m.group(1).replace(' ', '').replace(',', '.')); e = m.group(2) or ''
    return v * {'млрд': 1e9, 'млн': 1e6, 'тыс': 1e3}.get(e, 1)
def polye(t, label, n=80):
    m = re.search(label + r'[^|]{0,30}\|[\s|]*([^|]{1,%d})' % n, t)
    return m.group(1).strip() if m else ''
KOD = re.compile(r'\b(\d{2}\.\d{2}(?:\.\d{1,2})?)\b')
lock = threading.Lock()
gotovo = {}
if os.path.exists(F):
    for l in open(F, encoding='utf-8'):
        try: d = json.loads(l); gotovo[d['inn']] = d
        except Exception: pass
c = sqlite3.connect(DB, timeout=120)
s_fakt = [r[0] for r in c.execute("select distinct inn from fakty where inn like '22%'")]
vse = c.execute("select inn, okved_osn, okved_vse, sayt from predpriyatiya where inn like '22%' and (status_egrul is null or status_egrul not like '%LIQUID%' and status_egrul not like '%иквид%')").fetchall()
c.close()
fk = set(s_fakt)
kand = [r[0] for r in vse if r[0] not in fk and CAND.match(r[1] or '')]
ost = [r[0] for r in vse if r[0] not in fk and r[0] not in set(kand)]
ochered = [i for i in s_fakt + kand + ost if i not in gotovo]
if TEST: ochered = ochered[:6]
print(f'очередь: с фактами {len(s_fakt)}, кандидатов {len(kand)}, остальных {len(ost)} | готово {len(gotovo)} | в очереди {len(ochered)}', flush=True)
f = open(F, 'a', encoding='utf-8'); schet = {'ok': 0, 'net': 0, 'err': 0}
def odin(par):
    k, inn = par
    if time.time() - T0 > BUDGET: return
    S = requests.Session(); S.headers.update(UA); px = prox(k)
    d = {'inn': inn, 'ts': TS}
    try:
        r = S.get('https://checko.ru/search?query=' + inn, proxies=px, timeout=45, verify=False, allow_redirects=True)
        if r.status_code == 429:
            px = prox(k + 17); r = S.get('https://checko.ru/search?query=' + inn, proxies=px, timeout=45, verify=False, allow_redirects=True)
        if r.status_code != 200 or '/company/' not in r.url:
            d['err'] = f'нет карточки {r.status_code} {r.url[-60:]}'
            with lock: schet['net'] += 1; f.write(json.dumps(d, ensure_ascii=False) + '\n'); f.flush()
            return
        url = r.url.split('?')[0]; d['url'] = url
        t = tekst(r.text)
        m = re.search(r'/company/[a-z0-9\-]+-(\d{13,15})', url); d['ogrn'] = m.group(1) if m else ''
        d['nazvanie'] = (re.search(r'<title>([^<]{3,150})', r.text) or [0, ''])[1].split(',')[0].split(' - ')[0].strip()
        d['status'] = polye(t, 'Статус', 60)
        d['sayt'] = (SAYT.findall(t) or [''])[0]
        d['vyruchka'] = polye(t, 'Выручка', 40); d['pribyl'] = polye(t, 'Чистая прибыль', 40) or polye(t, 'Прибыль', 40)
        d['ssch'] = polye(t, 'Среднесписочная численность', 30) or polye(t, 'Численность', 30)
        d['nalogi'] = polye(t, 'Уплачено налогов', 40) or polye(t, 'Налоги', 40)
        d['god'] = (re.search(r'Выручка[^|]{0,40}\|[^|]{0,40}?(\d{4})', t) or [0, ''])[1]
        d['okved_osn'] = polye(t, 'Основной вид деятельности', 200) or polye(t, 'ОКВЭД', 120)
        d['adres'] = polye(t, 'Адрес', 200) or polye(t, 'Юридический адрес', 200)
        d['rukovoditel'] = polye(t, 'Руководитель', 120) or polye(t, 'Директор', 120)
        time.sleep(0.3)
        r2 = S.get(url + '/activity', proxies=px, timeout=45, verify=False)
        if r2.status_code == 200:
            t2 = tekst(r2.text); m = re.search(r'Виды деятельности|Коды ОКВЭД|ОКВЭД', t2)
            kusok = t2[m.start():m.start() + 12000] if m else t2
            kody = []
            for kd in KOD.findall(kusok):
                if kd not in kody and not re.match(r'^(1\.|2\.|3\.)', kd): kody.append(kd)
            d['okved_vse'] = kody[:80]
        time.sleep(0.3)
        r3 = S.get(url + '/contacts', proxies=px, timeout=45, verify=False)
        if r3.status_code == 200:
            t3 = tekst(r3.text)
            d['sayt'] = d['sayt'] or (SAYT.findall(t3) or [''])[0]
            d['telefony'] = sorted(set(TEL.findall(t3)))[:6]
            d['pochty'] = sorted({e for e in POCHTA.findall(t3) if not CHUZHIE.search(e)})[:6]
        with lock: schet['ok'] += 1
    except Exception as e:
        d['err'] = repr(e)[:120]
        with lock: schet['err'] += 1
    with lock:
        f.write(json.dumps(d, ensure_ascii=False) + '\n'); f.flush()
with ThreadPoolExecutor(4) as ex:
    list(ex.map(odin, enumerate(ochered)))
f.close()
print('за заход:', schet, '| прошло', round(time.time() - T0), 'с', flush=True)
# влив
c = sqlite3.connect(DB, timeout=120); n_u = n_f = 0
for l in open(F, encoding='utf-8'):
    try: d = json.loads(l)
    except Exception: continue
    if d.get('err') or not d.get('url'): continue
    inn = d['inn']
    okv = '|'.join(d.get('okved_vse') or [])
    c.execute("""update predpriyatiya set sayt=coalesce(nullif(sayt,''),?), okved_osn=coalesce(nullif(okved_osn,''),?), okved_vse=case when length(coalesce(okved_vse,''))<length(?) then ? else okved_vse end,
                 ssch=coalesce(ssch,?), rukovoditel=coalesce(nullif(rukovoditel,''),?), status_egrul=coalesce(nullif(status_egrul,''),?), adres=coalesce(nullif(adres,''),?),
                 istochniki_zapisi=case when instr(coalesce(istochniki_zapisi,''),'checko')>0 then istochniki_zapisi else coalesce(istochniki_zapisi,'')||'|checko' end where inn=?""",
              (d.get('sayt') or None, (KOD.search(d.get('okved_osn') or '') or [None, None])[1] if d.get('okved_osn') else None, okv, okv,
               int(re.sub(r'\D', '', d.get('ssch') or '') or 0) or None, d.get('rukovoditel') or None, d.get('status') or None, d.get('adres') or None, inn)); n_u += 1
    v = chislo(d.get('vyruchka')); pb = chislo(d.get('pribyl')); nl = chislo(d.get('nalogi'))
    if v is not None or pb is not None or nl is not None:
        c.execute('insert or replace into finansy values(?,?,?,?,?,?,?,?)', (inn, 'checko', d.get('god') or '', v, pb, nl, int(re.sub(r'\D', '', d.get('ssch') or '') or 0) or None, TS)); n_f += 1
c.commit()
print(f'влито: обновлено предприятий {n_u}, строк финансов {n_f} | всего в checko.jsonl {len(gotovo) + schet["ok"] + schet["net"] + schet["err"]}', flush=True)
c.close()
if not TEST and not ochered: print('ГОТОВО')
