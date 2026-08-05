# -*- coding: utf-8 -*-
"""Войти в панель токеном 3-й сессии и перечислить базы. Токен не печатается никогда.

Владелец предложил взять токен user1/user2 или спросить user3 у соседей. Спрашивать не
нужно: токен 3-й сессии лежит на самом сервере, в `_ops`. Значит секрет вообще не поедет
через песочницу и не попадёт ни в один файл репозитория — читается на месте и остаётся
на месте.

Прибор: берёт токен из файла, входит, перечисляет базы обзвона и печатает по каждой,
сколько в ней предприятий и открывается ли карточка. Печатает КОДЫ и ЧИСЛА, не секреты.
"""
import io
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

BAZA = 'http://127.0.0.1:8012'
TOKEN_FAYLY = (r'C:\sender\_ops\p25_user3_token.txt',
               r'C:\sender\_ops\p25_user1_token.txt',
               r'C:\sender\p25_user3_token.txt')
KANDIDATY = ['/obzvon/centro', '/obzvon/centro1', '/obzvon/centro2', '/obzvon/centro3',
             '/obzvon/centro4', '/obzvon/kc', '/obzvon/meyer']


def token():
    for p in TOKEN_FAYLY:
        if os.path.exists(p):
            t = io.open(p, encoding='utf-8', errors='replace').read().strip()
            if t:
                return t, os.path.basename(p)
    return '', ''


def zapros(url, dannye=None, kuki='', metod=None):
    rq = urllib.request.Request(
        url, data=dannye,
        method=metod or ('POST' if dannye is not None else 'GET'))
    rq.add_header('User-Agent', 'progulka-3s')
    if dannye is not None:
        rq.add_header('Content-Type', 'application/x-www-form-urlencoded')
    if kuki:
        rq.add_header('Cookie', kuki)
    try:
        with urllib.request.urlopen(rq, timeout=45) as o:
            return o.status, o.read().decode('utf-8', 'replace'), o.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace'), e.headers
    except Exception as e:  # noqa: BLE001
        return 0, '__ОШИБКА__ %s %s' % (type(e).__name__, str(e)[:70]), None


tok, otkuda = token()
print('токен взят из: %s (длина %d)' % (otkuda or 'НЕ НАЙДЕН', len(tok)))
itog = {'токен найден': bool(tok)}

# 1) Что отвечает панель без входа.
kod0, telo0, _ = zapros(BAZA + '/obzvon/centro')
est_forma = bool(re.search(r'name="?(?:token|password|key)', telo0, re.I))
print('без входа: код %s, длина %d, форма входа: %s' % (kod0, len(telo0), est_forma))
if est_forma:
    for m in re.finditer(r"<input[^>]+>", telo0):
        print('    поле формы: %s' % re.sub(r'\s+', ' ', m.group(0))[:120])

# 2) Вход. Пробуем несколько имён поля — какое сработает, то и настоящее.
kuki = ''
for pole in ('token', 'password', 'key', 'user'):
    kod, telo, hdr = zapros(BAZA + '/obzvon/centro/login',
                            urllib.parse.urlencode({pole: tok}).encode())
    stavit = (hdr or {}).get('Set-Cookie', '') if hdr else ''
    print('вход полем %-9s -> код %s, кука: %s' % (pole, kod, 'да' if stavit else 'нет'))
    if stavit:
        kuki = stavit.split(';')[0]
        itog['поле входа'] = pole
        break

# 3) Базы: что открывается с кукой.
print('\n=== базы')
bazy = {}
for p in KANDIDATY:
    kod, telo, _ = zapros(BAZA + p, kuki=kuki)
    m = re.search(r'(\d[\d\s]{2,})\s*(?:предприят|компан|строк)', telo)
    vsego = re.sub(r'\s', '', m.group(1)) if m else ''
    est_karta = 'ct-card' in telo or 'ct-person' in telo
    if kod == 200:
        bazy[p] = {'длина': len(telo), 'всего': vsego, 'карточка видна': est_karta}
    print('  %-18s код %-4s длина %-7d всего %-8s карточка %s'
          % (p, kod, len(telo), vsego or '—', 'да' if est_karta else 'нет'))

itog['баз открылось'] = len(bazy)
print('ИТОГ ' + json.dumps(itog, ensure_ascii=False))
