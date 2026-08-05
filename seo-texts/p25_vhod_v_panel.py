# -*- coding: utf-8 -*-
"""Войти в панель и открыть настоящую страницу. Не базу — то, что видит продавец.

Владелец спрашивает, ходила ли я по панели глазами. Не ходила: чужой экран показывал
чужую сессию. Хожу.

Ходить надо по ЖИВОЙ странице, а не по базе: между базой и глазами стоят запрос, шаблон
и отбор, и именно там сегодня нашлась дырка — карточка печатала должность из поля,
которого в таблице нет. База сказала бы «должности есть», глаз говорит «значок пуст».

Прибор: находит, чем панель пускает, пробует зайти и печатает, что вернулось. Ничего не
меняет.
"""
import io
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

BAZA = 'http://127.0.0.1:8012'
PUTI = ('/obzvon/centro', '/obzvon/centro1', '/obzvon/kc', '/obzvon/meyer', '/')


def zapros(url, dannye=None, kuki=''):
    rq = urllib.request.Request(url, data=dannye, method='POST' if dannye else 'GET')
    rq.add_header('User-Agent', 'proverka-3s')
    if kuki:
        rq.add_header('Cookie', kuki)
    try:
        with urllib.request.urlopen(rq, timeout=40) as o:
            return o.status, o.read().decode('utf-8', 'replace'), o.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace'), e.headers
    except Exception as e:  # noqa: BLE001
        return 0, '__ОШИБКА__ %s: %s' % (type(e).__name__, str(e)[:80]), {}


itog = {}
print('=== что отвечает панель без входа')
for p in PUTI:
    kod, telo, hdr = zapros(BAZA + p)
    priznak = ('форма входа' if re.search(r'<form[^>]*login|name="password"', telo, re.I)
               else ('карточки/список' if 'ct-card' in telo or 'obzvon' in telo.lower()
                     else telo[:60].replace('\n', ' ')))
    print('  %-18s %-4s %-7d %s' % (p, kod, len(telo), priznak))
    itog[p] = kod

# Где объявлен вход и какие имена/пароли он читает.
print('\n=== код входа')
for put in (r'C:\seostat\app\api\routes_centro.py', r'C:\seostat\app\main.py',
            r'C:\seostat\app\api\routes_obzvon.py'):
    if not os.path.exists(put):
        continue
    t = io.open(put, encoding='utf-8', errors='replace').read()
    for m in re.finditer(r'.{0,90}(?:login|password|USERS|getenv|environ).{0,90}', t):
        s = re.sub(r'\s+', ' ', m.group(0)).strip()
        if re.search(r'login|password|USERS|PANEL', s, re.I):
            print('  %s: %s' % (os.path.basename(put), s[:150]))

# Переменные окружения сервера, похожие на вход в панель.
print('\n=== переменные окружения (только ИМЕНА, значения не печатаю)')
print('  ' + ', '.join(sorted(k for k in os.environ
                              if re.search(r'PANEL|OBZVON|USER|PASS|AUTH|LOGIN', k, re.I))))

print('ИТОГ ' + json.dumps(itog, ensure_ascii=False))
