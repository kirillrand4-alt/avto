# -*- coding: utf-8 -*-
r"""fixK (сервер, только чтение): статус юрлиц РФ из ЕГРЮЛ через DaData findById/party по ИНН.

Список ИНН – файл на дропе (по строке), результат – JSON на дроп. Токен – из окружения сервера или
rs.env раннера; НЕ печатается. 6 потоков, повтор на сбой, головная организация (branch_type MAIN).

    python3 zapusk_na_servere.py fixK_dadata.py fixK-proverka-rf.txt fixK-dadata.json
"""
import io
import json
import os
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

DROP = r'C:\seostat\drop\drop-storage'
VHOD, VYHOD = sys.argv[1], sys.argv[2]
TOKEN = os.environ.get('DADATA_TOKEN', '').strip()
if not TOKEN:
    for put in (r'C:\sender\rs.env', r'C:\sender\server\rs.env', r'C:\sender\runner-secrets.env',
                r'C:\sender\server\runner-secrets.env', os.path.join(DROP, 'runner-secrets.env')):
        try:
            for st in io.open(put, encoding='utf-8', errors='replace'):
                if st.strip().startswith('DADATA_TOKEN'):
                    TOKEN = st.split('=', 1)[1].strip().strip('"\'')
                    break
        except OSError:
            pass
        if TOKEN:
            break
print('токен dadata: %s' % ('есть' if TOKEN else 'НЕТ'))
if not TOKEN:
    raise SystemExit(2)
URL = 'https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party'
inny = [x.strip() for x in io.open(os.path.join(DROP, VHOD), encoding='utf-8') if x.strip()]
print('ИНН: %d' % len(inny))


def sprosit(inn):
    telo = json.dumps({'query': inn, 'count': 5, 'branch_type': 'MAIN'}).encode()
    req = urllib.request.Request(URL, data=telo, headers={'Content-Type': 'application/json', 'Accept': 'application/json',
                                                          'Authorization': 'Token ' + TOKEN})
    return json.loads(urllib.request.urlopen(req, timeout=30).read().decode('utf-8'))


def odno(inn):
    for pop in range(4):
        try:
            o = sprosit(inn)
            break
        except Exception as e:  # noqa: BLE001
            if pop == 3:
                return inn, {'oshibka': '%s: %s' % (type(e).__name__, str(e)[:100])}
            time.sleep(2 * (pop + 1))
    sug = [x for x in (o.get('suggestions') or []) if (x.get('data') or {}).get('inn') == inn]
    if not sug:
        return inn, {'net': 1}
    d = sug[0]['data']
    st = d.get('state') or {}
    m = d.get('management') or {}
    adr = d.get('address') or {}
    fin = d.get('finance') or {}
    return inn, {'nazvanie': sug[0].get('value'), 'status': st.get('status'), 'code': st.get('code'),
                 'liquidation_date': st.get('liquidation_date'), 'actuality_date': st.get('actuality_date'),
                 'registration_date': st.get('registration_date'), 'adres': adr.get('value'),
                 'region': ((adr.get('data') or {}).get('region_with_type')), 'okved': d.get('okved'),
                 'ruk': m.get('name'), 'ruk_dolzhnost': m.get('post'), 'ssch': d.get('employee_count'),
                 'vyruchka': fin.get('income'), 'fin_god': fin.get('year'), 'ogrn': d.get('ogrn'), 'kpp': d.get('kpp'),
                 'opf': (d.get('opf') or {}).get('short'), 'tip': d.get('type')}


rez = {}
lok = threading.Lock()
t0 = time.time()
with ThreadPoolExecutor(max_workers=6) as pool:
    for n, (inn, z) in enumerate(pool.map(odno, inny), 1):
        with lok:
            rez[inn] = z
io.open(os.path.join(DROP, VYHOD), 'w', encoding='utf-8').write(json.dumps(rez, ensure_ascii=False))
sch = {}
for z in rez.values():
    k = z.get('status') or ('нет в выдаче' if z.get('net') else 'ошибка')
    sch[k] = sch.get(k, 0) + 1
print('готово за %.0f с: %s -> %s' % (time.time() - t0, sch, VYHOD))
