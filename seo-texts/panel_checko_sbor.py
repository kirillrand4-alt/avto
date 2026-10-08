# -*- coding: utf-8 -*-
r"""Страницы checko.ru по всем компаниям панели Meyer (владелец 08.10: «заполни эти поля
информацией из чеко» – адрес, директор, статус ЕГРЮЛ, почта, прибыль, сотрудники).

Только скачивание, разбор отдельно (panel_checko_razbor.py): страницы лежат на сервере, их можно
разбирать повторно без новых запросов к checko.
  проход 1 – карточка компании (search?query=ИНН -> /company/...), gzip-HTML на ИНН;
  проход 2 – /company/<ОГРН>/contacts, только где на карточке «Еще N номер/адреса».
Прокси владельца и бережный темп – из cc_checko_proxy (не чаще раза в 3 с на прокси,
на 429 – ротация IP и пауза). Мёртвый прокси при старте один раз ротируется.
Повторяемо: уже скачанное не качается. Запуск без ключа – отцепленный процесс и выход;
--rabota – сама работа; --status – сколько готово.
"""
import gzip
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile

DIR = r'C:\sender\server'
PAPKA = os.path.join(DIR, 'checko_meyer')
LOG = os.path.join(PAPKA, '_sbor.log')
KAT = r'C:\centro2\data\meyer_baza1.db'
DROP = r'C:\seostat\drop\drop-storage'


def log(*a):
    s = time.strftime('%H:%M:%S ') + ' '.join(str(x) for x in a)
    with io.open(LOG, 'a', encoding='utf-8') as f:
        f.write(s + '\n')


def inny():
    k = sqlite3.connect('file:%s?mode=ro' % KAT, uri=True)
    return [r[0] for r in k.execute('select inn from company order by inn')]


def status():
    vse = inny()
    est = set(f.split('.')[0] for f in os.listdir(PAPKA) if f.endswith('.html.gz')) if os.path.isdir(PAPKA) else set()
    glav = [i for i in vse if i in est]
    print(json.dumps({'vsego': len(vse), 'kartochek': len(glav), 'kontaktov': len([f for f in est if f.endswith('-kontakty')]),
                      'hvost_loga': io.open(LOG, encoding='utf-8').read()[-1500:] if os.path.exists(LOG) else ''},
                     ensure_ascii=False))


def rabota():
    sys.path.insert(0, DIR)
    import cc_checko_proxy as CP
    os.makedirs(PAPKA, exist_ok=True)
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
    log('прокси живых', len(zhivye))
    if not zhivye:
        return
    vse = inny()
    lok = threading.Lock()
    n = [0, 0]

    def put(imya):
        return os.path.join(PAPKA, imya + '.html.gz')

    def sohranit(imya, html):
        tmp = put(imya) + '.tmp'
        with gzip.open(tmp, 'wt', encoding='utf-8') as f:
            f.write(html)
        os.replace(tmp, put(imya))

    def rabotnik(k):
        p = zhivye[k]
        while True:
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
                    log('сбой', imya, kod)
                if n[0] % 25 == 0:
                    log('готово', n[0], 'сбоев', n[1])

    for prohod in (1, 2):
        if prohod == 1:
            ochered = [('https://checko.ru/search?query=%s' % i, i) for i in vse if not os.path.exists(put(i))]
        else:
            ochered = []
            for i in vse:
                if not os.path.exists(put(i)) or os.path.exists(put(i + '-kontakty')):
                    continue
                h = gzip.open(put(i), 'rt', encoding='utf-8').read()
                m = re.search(r'href="(/company/\d{13}/contacts)">Еще \d+', h)
                if m:
                    ochered.append(('https://checko.ru' + m.group(1), i + '-kontakty'))
        log('проход', prohod, 'в очереди', len(ochered))
        n[0] = n[1] = 0
        potoki = [threading.Thread(target=rabotnik, args=(k,)) for k in range(len(zhivye))]
        for t in potoki:
            t.start()
        for t in potoki:
            t.join()
        log('проход', prohod, 'завершён, сбоев', n[1])
    arh = os.path.join(DROP, 'checko-meyer-html.zip')
    with zipfile.ZipFile(arh + '.tmp', 'w', zipfile.ZIP_STORED) as z:
        for f in sorted(os.listdir(PAPKA)):
            if f.endswith('.html.gz'):
                z.write(os.path.join(PAPKA, f), f)
    os.replace(arh + '.tmp', arh)
    log('ГОТОВО, архив на дропе')


if __name__ == '__main__':
    if '--rabota' in sys.argv:
        try:
            rabota()
        except Exception as e:  # noqa: BLE001
            log('ОШИБКА', repr(e)[:300])
    elif '--status' in sys.argv:
        status()
    else:
        os.makedirs(PAPKA, exist_ok=True)
        kopiya = os.path.join(PAPKA, '_sbor.py')  # копия скрипта: файл задания может быть удалён
        io.open(kopiya, 'w', encoding='utf-8').write(io.open(os.path.abspath(__file__), encoding='utf-8').read())
        subprocess.Popen([sys.executable, kopiya, '--rabota'], cwd=DIR,
                         creationflags=0x00000008 | 0x00000200, close_fds=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        print('запущен отцепленно; лог', LOG)
