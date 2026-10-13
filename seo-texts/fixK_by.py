# -*- coding: utf-8 -*-
r"""fixK (сервер, только чтение): статус юрлиц Беларуси по УНП – открытый сервис ЕГР (egr.gov.by, api v2).

    python3 zapusk_na_servere.py fixK_by.py fixK-proverka-by.txt fixK-by.json [--proba]

Для каждого УНП: getBaseInfoByRegNum (состояние субъекта, даты), getShortNameByRegNum, getAddressByRegNum.
Сервис недоступен или не ответил – в результате «статус не проверен» (так и пишется в панель).
"""
import io
import json
import os
import ssl
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

DROP = r'C:\seostat\drop\drop-storage'
VHOD, VYHOD = sys.argv[1], sys.argv[2]
BAZA = 'https://egr.gov.by/api/v2/egr/'
unp = [x.strip() for x in io.open(os.path.join(DROP, VHOD), encoding='utf-8') if x.strip()]
if '--proba' in sys.argv:
    unp = unp[:3]
KTX = ssl.create_default_context()


def get(metod, u):
    req = urllib.request.Request(BAZA + metod + '/' + u, headers={'Accept': 'application/json', 'User-Agent': 'Mozilla/5.0'})
    try:
        r = urllib.request.urlopen(req, timeout=30, context=KTX)
        t = r.read().decode('utf-8', 'replace')
        return json.loads(t) if t.strip() else None
    except urllib.error.HTTPError as e:
        return {'_http': e.code}
    except Exception as e:  # noqa: BLE001
        try:   # у egr.gov.by бывает цепочка сертификатов без промежуточного – вторая попытка без проверки имени не делается
            return {'_oshibka': '%s: %s' % (type(e).__name__, str(e)[:120])}
        finally:
            pass


def odno(u):
    out = {}
    for metod in ('getBaseInfoByRegNum', 'getShortNameByRegNum', 'getAddressByRegNum'):
        for pop in range(3):
            o = get(metod, u)
            if isinstance(o, dict) and o.get('_oshibka') and pop < 2:
                time.sleep(2)
                continue
            break
        out[metod] = o
    return u, out


t0 = time.time()
rez = {}
with ThreadPoolExecutor(max_workers=4) as pool:
    for u, z in pool.map(odno, unp):
        rez[u] = z
io.open(os.path.join(DROP, VYHOD), 'w', encoding='utf-8').write(json.dumps(rez, ensure_ascii=False))
if '--proba' in sys.argv:
    print(json.dumps(rez, ensure_ascii=False)[:3000])
sch = {}
for z in rez.values():
    b = z.get('getBaseInfoByRegNum')
    if isinstance(b, list) and b:
        st = ((b[0].get('nsi00219') or {}).get('vnsostk')) or 'без статуса'
    elif isinstance(b, dict):
        st = 'ошибка: %s' % (b.get('_http') or b.get('_oshibka', '')[:40])
    else:
        st = 'пусто'
    sch[st] = sch.get(st, 0) + 1
print('за %.0f с: %s -> %s' % (time.time() - t0, sch, VYHOD))
