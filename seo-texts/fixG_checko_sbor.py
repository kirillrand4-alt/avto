# -*- coding: utf-8 -*-
r"""fixG: страницы checko.ru по КАНДИДАТАМ на замену 13 помеченных компаний (их ещё нет в каталоге).

Копия panel_checko_sbor.py (прокси владельца cc_checko_proxy, не чаще раза в 3 с на прокси, на 429 –
ротация), отличия: список ИНН – аргументом (через запятую), своя папка
C:\sender\server\checko_meyer_fixG\, работа в этом же прогоне (кандидатов десятки, не сотни),
бюджет времени 1400 с. Проход 1 – карточка (search?query=ИНН), проход 2 – «Контакты», где «Еще N».
Повторяемо: скачанное не качается. Итог – архив fixG-checko-html.zip на дроп.

    python3 zapusk_na_servere.py fixG_checko_sbor.py <ИНН,ИНН,...>
"""
import gzip
import io
import json
import os
import re
import sys
import threading
import time
import urllib.request
import zipfile

DIR = r'C:\sender\server'
PAPKA = os.path.join(DIR, 'checko_meyer_fixG')
DROP = r'C:\seostat\drop\drop-storage'
T0 = time.time()
BYUDZHET = 1400
os.makedirs(PAPKA, exist_ok=True)
INNY = [x.strip() for x in sys.argv[1].split(',') if re.fullmatch(r'\d{10}|\d{12}', x.strip())]
print('ИНН в задании: %d' % len(INNY))
sys.path.insert(0, DIR)
import cc_checko_proxy as CP  # noqa: E402

zhivye = []
for x in json.load(open(os.path.join(DIR, 'checko-proxies.json'))):
    p = CP.Прокси(x)
    kod = p.get('https://checko.ru/')[0]
    if kod != 200:
        try:
            urllib.request.urlopen(x['rotate'], timeout=40).read()
        except Exception:  # noqa: BLE001
            pass
        time.sleep(25)
        kod = p.get('https://checko.ru/')[0]
    if kod == 200:
        zhivye.append(p)
print('прокси живых: %d' % len(zhivye))
if not zhivye:
    raise SystemExit(2)


def put(imya):
    return os.path.join(PAPKA, imya + '.html.gz')


def sohranit(imya, html):
    tmp = put(imya) + '.tmp'
    with gzip.open(tmp, 'wt', encoding='utf-8') as f:
        f.write(html)
    os.replace(tmp, put(imya))


lok = threading.Lock()
n = [0, 0]
ochered = []


def rabotnik(k):
    p = zhivye[k]
    while time.time() - T0 < BYUDZHET:
        with lok:
            if not ochered:
                return
            url, imya = ochered.pop(0)
        kod, html = p.get(url)
        with lok:
            n[0] += 1
            if kod == 200 and html:
                sohranit(imya, html)
            else:
                n[1] += 1
                print('сбой', imya, kod)


for prohod in (1, 2):
    if prohod == 1:
        ochered[:] = [('https://checko.ru/search?query=%s' % i, i) for i in INNY if not os.path.exists(put(i))]
    else:
        ochered[:] = []
        for i in INNY:
            if not os.path.exists(put(i)) or os.path.exists(put(i + '-kontakty')):
                continue
            h = gzip.open(put(i), 'rt', encoding='utf-8').read()
            m = re.search(r'href="(/company/\d{13}/contacts)">Еще \d+', h)
            if m:
                ochered.append(('https://checko.ru' + m.group(1), i + '-kontakty'))
    print('проход %d: в очереди %d' % (prohod, len(ochered)))
    n[0] = n[1] = 0
    potoki = [threading.Thread(target=rabotnik, args=(k,)) for k in range(len(zhivye))]
    for t in potoki:
        t.start()
    for t in potoki:
        t.join()
    print('проход %d: запросов %d, сбоев %d, %d с' % (prohod, n[0], n[1], time.time() - T0))
arh = os.path.join(DROP, 'fixG-checko-html.zip')
with zipfile.ZipFile(arh + '.tmp', 'w', zipfile.ZIP_STORED) as z:
    for f in sorted(os.listdir(PAPKA)):
        if f.endswith('.html.gz'):
            z.write(os.path.join(PAPKA, f), f)
os.replace(arh + '.tmp', arh)
est = [i for i in INNY if os.path.exists(put(i))]
print('карточек есть %d из %d; нет: %s' % (len(est), len(INNY), [i for i in INNY if i not in est]))
print('архив: fixG-checko-html.zip')
