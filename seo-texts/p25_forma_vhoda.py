# -*- coding: utf-8 -*-
"""Разобрать форму входа centro: куда постит и какие поля. И войти через неё.

Понято: базы kc/meyer отдают 401 Basic, а centro/centro1/centro2 отдают HTML-ФОРМУ
(код 200 с полями username/password). Это разные входы. Для centro Basic-заголовок не
тот механизм — нужна отправка формы, которая ставит сессионную куку. Первый инстинкт был
верным, но я не знала адрес, куда форма шлёт, и слала на угаданный /login.

Прибор: берёт форму, печатает её action, method и имена полей; затем постит туда логин
и пароль из серверного токен-файла (значения не печатаются) и проверяет, открылась ли
очередь. Банка кук ловит сессию через перенаправления.
"""
import http.cookiejar
import io
import json
import os
import re
import urllib.parse
import urllib.request

PANEL = 'http://127.0.0.1:8012'
TOKEN_FAYL = r'C:\sender\_ops\p25_user3_token.txt'
banka = http.cookiejar.CookieJar()
otk = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(banka))


def vzyat(url, dannye=None):
    rq = urllib.request.Request(url, data=dannye,
                                method='POST' if dannye is not None else 'GET')
    rq.add_header('User-Agent', 'progulka-3s')
    if dannye is not None:
        rq.add_header('Content-Type', 'application/x-www-form-urlencoded')
    try:
        with otk.open(rq, timeout=45) as o:
            return o.status, o.read().decode('utf-8', 'replace'), o.geturl()
    except urllib.error.HTTPError as e:  # noqa: F821
        return e.code, e.read().decode('utf-8', 'replace'), url
    except Exception as e:  # noqa: BLE001
        return 0, '__ОШИБКА__ %s' % type(e).__name__, url


kod, telo, _ = vzyat(PANEL + '/obzvon/centro')
print('centro без входа: код %d, длина %d' % (kod, len(telo)))
forma = re.search(r'<form[^>]*>', telo, re.I)
print('тег формы: %s' % (forma.group(0) if forma else 'НЕТ'))
action = ''
if forma:
    m = re.search(r'action="([^"]*)"', forma.group(0), re.I)
    action = m.group(1) if m else ''
    mm = re.search(r'method="([^"]*)"', forma.group(0), re.I)
    print('  action=«%s» method=%s' % (action or '(тот же адрес)', mm.group(1) if mm else 'GET'))
polya = re.findall(r'<input[^>]*name="([^"]+)"', telo, re.I)
print('  поля формы: %s' % ', '.join(polya))

# Логин/пароль из файла.
login = parol = ''
if os.path.exists(TOKEN_FAYL):
    for s in io.open(TOKEN_FAYL, encoding='utf-8', errors='replace').read().split('\n'):
        m = re.match(r'\s*(?:логин|login)\s*[:=]\s*(\S.*)$', s, re.I)
        if m:
            login = m.group(1).strip()
        m = re.match(r'\s*(?:пароль|password)\s*[:=]\s*(\S.*)$', s, re.I)
        if m:
            parol = m.group(1).strip()
for kus in os.environ.get('PANEL_LOGINS', '').replace(',', '\n').split('\n'):
    if '=' in kus and not login:
        login, parol = kus.split('=', 1)

# Куда постить: action, если абсолютный/относительный, иначе тот же адрес.
if action.startswith('http'):
    cel = action
elif action.startswith('/'):
    cel = PANEL + action
elif action:
    cel = PANEL + '/obzvon/' + action
else:
    cel = PANEL + '/obzvon/centro'
print('\nпощу на: %s логином «%s» (пароль скрыт, длина %d)'
      % (cel, login or '—', len(parol)))

itog = {'форма найдена': bool(forma), 'action': action}
if login and parol:
    kod, telo, konec = vzyat(cel, urllib.parse.urlencode(
        {'username': login.strip(), 'password': parol.strip()}).encode())
    forma_posle = bool(re.search(r'name="?password', telo, re.I))
    # Проверяем очередь после входа.
    kod2, ochered, _ = vzyat(PANEL + '/obzvon/centro')
    forma2 = bool(re.search(r'name="?password', ochered, re.I))
    voshli = kod2 == 200 and not forma2
    print('после входа: код поста %d, финальный адрес %s' % (kod, konec[-40:]))
    print('очередь: код %d, форма входа осталась: %s -> ВОШЛИ: %s'
          % (kod2, forma2, voshli))
    itog.update({'вошли': voshli, 'кук в банке': len(banka)})
    if voshli:
        # Что видно: сколько строк в очереди.
        m = re.search(r'(?:всего|найдено)\D{0,12}(\d[\d\s]{0,9})', ochered, re.I)
        itog['строк в очереди'] = re.sub(r'\s', '', m.group(1)) if m else '?'
print('ИТОГ ' + json.dumps(itog, ensure_ascii=False))
