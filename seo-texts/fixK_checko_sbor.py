# -*- coding: utf-8 -*-
r"""fixK (сервер, только чтение checko.ru): страницы checko по кандидатам MEYER-7 (РФ) – реквизиты, руководитель,
статус, ССЧ, выручка/прибыль за последний год (разбор – panel_checko_razbor.py локально).

Копия panel_checko_sbor.py: прокси владельца cc_checko_proxy (не чаще раза в 3 с на прокси, на 429 – ротация),
отцепленный процесс с продолжением; отличия – список ИНН из файла на дропе (порядок = приоритет), своя папка
C:\sender\server\checko_meyer_fixK\, уже скачанные другими прогонами страницы (checko_meyer, checko_meyer_fixG)
не качаются заново – копируются. Проход 1 – карточка, проход 2 – «Контакты», где «Еще N» (только почты).
Архив – fixK-checko-html.zip на дроп (по ходу – каждые 200 карточек).

    python3 zapusk_na_servere.py fixK_checko_sbor.py fixK-proverka-checko.txt     # запуск отцепленно
    python3 zapusk_na_servere.py fixK_checko_sbor.py --status
    python3 zapusk_na_servere.py fixK_checko_sbor.py --arhiv                      # архив того, что есть
"""
import gzip
import io
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile

DIR = r'C:\sender\server'
PAPKA = os.path.join(DIR, 'checko_meyer_fixK')
LOG = os.path.join(PAPKA, '_sbor.log')
SPISOK = os.path.join(PAPKA, '_spisok.txt')
DROP = r'C:\seostat\drop\drop-storage'
STARYE = [os.path.join(DIR, 'checko_meyer'), os.path.join(DIR, 'checko_meyer_fixG')]
ARH = os.path.join(DROP, 'fixK-checko-html.zip')


def log(*a):
    s = time.strftime('%H:%M:%S ') + ' '.join(str(x) for x in a)
    with io.open(LOG, 'a', encoding='utf-8') as f:
        f.write(s + '\n')


def put(imya):
    return os.path.join(PAPKA, imya + '.html.gz')


def inny():
    return [x.strip() for x in io.open(SPISOK, encoding='utf-8') if re.fullmatch(r'\d{10}|\d{12}', x.strip())]


def arhiv():
    with zipfile.ZipFile(ARH + '.tmp', 'w', zipfile.ZIP_STORED) as z:
        for f in sorted(os.listdir(PAPKA)):
            if f.endswith('.html.gz'):
                z.write(os.path.join(PAPKA, f), f)
    os.replace(ARH + '.tmp', ARH)


def status():
    vse = inny() if os.path.exists(SPISOK) else []
    est = set(f[:-8] for f in os.listdir(PAPKA) if f.endswith('.html.gz')) if os.path.isdir(PAPKA) else set()
    print(json.dumps({'vsego': len(vse), 'kartochek': sum(1 for i in vse if i in est),
                      'kontaktov': len([f for f in est if f.endswith('-kontakty')]),
                      'hvost_loga': io.open(LOG, encoding='utf-8').read()[-1200:] if os.path.exists(LOG) else ''},
                     ensure_ascii=False))


def rabota():
    sys.path.insert(0, DIR)
    import cc_checko_proxy as CP
    vse = inny()
    # уже скачанное другими прогонами – копией, без запроса
    n_kop = 0
    for i in vse:
        for imya in (i, i + '-kontakty'):
            if os.path.exists(put(imya)):
                continue
            for st in STARYE:
                p = os.path.join(st, imya + '.html.gz')
                if os.path.exists(p):
                    shutil.copy(p, put(imya))
                    n_kop += 1
                    break
    log('скопировано из прежних прогонов', n_kop)
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
    lok = threading.Lock()
    n = [0, 0]
    ochered = []

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
                if n[0] % 200 == 0:
                    try:
                        arhiv()
                    except Exception as e:  # noqa: BLE001
                        log('архив не записан', repr(e)[:100])

    for prohod in ((1,) if os.path.exists(os.path.join(PAPKA, '_tolko_kartochki')) else (1, 2)):
        if prohod == 1:
            ochered[:] = [('https://checko.ru/search?query=%s' % i, i) for i in vse if not os.path.exists(put(i))]
        else:
            ochered[:] = []
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
        arhiv()
    log('ГОТОВО, архив на дропе')


if __name__ == '__main__':
    os.makedirs(PAPKA, exist_ok=True)
    if '--rabota' in sys.argv:
        try:
            rabota()
        except Exception as e:  # noqa: BLE001
            log('ОШИБКА', repr(e)[:300])
    elif '--status' in sys.argv:
        status()
    elif '--arhiv' in sys.argv:
        arhiv()
        print('архив: %s (%d байт)' % (ARH, os.path.getsize(ARH)))
    elif '--stop' in sys.argv:
        # остановить отцепленный сбор (после прохода 1): процесс python с _sbor.py этой папки
        r = subprocess.run(['powershell', '-NoProfile', '-Command',
                            "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*checko_meyer_fixK*_sbor.py*' } | "
                            "ForEach-Object { Stop-Process -Id $_.ProcessId -Force; $_.ProcessId }"], capture_output=True, text=True, timeout=120)
        print('остановлено:', r.stdout.strip(), r.stderr.strip()[:300])
        log('остановлен по --stop')
    else:
        if '--tolko-kartochki' in sys.argv:
            io.open(os.path.join(PAPKA, '_tolko_kartochki'), 'w').write('1')
        shutil.copy(os.path.join(DROP, sys.argv[1]), SPISOK)
        kopiya = os.path.join(PAPKA, '_sbor.py')  # копия скрипта: файл задания может быть удалён
        io.open(kopiya, 'w', encoding='utf-8').write(io.open(os.path.abspath(__file__), encoding='utf-8').read())
        subprocess.Popen([sys.executable, kopiya, '--rabota'], cwd=DIR,
                         creationflags=0x00000008 | 0x00000200, close_fds=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        print('запущен отцепленно: ИНН %d; лог %s' % (len(inny()), LOG))
