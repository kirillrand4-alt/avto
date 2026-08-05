# -*- coding: utf-8 -*-
"""Где на самом деле проверяется вход: страница-оболочка всегда отдаёт форму (554 байта),
а данные грузятся отдельными запросами. Проверяю Basic на data-роутах.

Пары из .env (admin, prodazhnik) на /obzvon/centro возвращали форму — потому что это
крошечная оболочка, она показывает login-box всегда, а карточки подтягиваются запросами
/card и /list. Значит вход надо проверять там: верный Basic -> 200 с данными, неверный
-> 401. Печатаю коды и длины по каждому пути и паре; пароли не печатаю.
"""
import base64
import io
import json
import os
import re
import urllib.error
import urllib.request

PANEL = 'http://127.0.0.1:8012'
PUTI = ('/obzvon/centro/list?page=1', '/obzvon/centro/card?skip=0',
        '/obzvon/centro/list', '/obzvon/centro?skip=0')


def pary():
    out = []
    for env in (r'C:\seostat\.env', r'C:\seostat\app\.env'):
        if os.path.exists(env):
            for s in io.open(env, encoding='utf-8', errors='replace').read().split('\n'):
                m = re.match(r'\s*obzvon_users\s*=\s*(.+)$', s, re.I)
                if m:
                    for para in m.group(1).strip().strip('"\'').split(','):
                        if ':' in para:
                            im, _, par = para.strip().partition(':')
                            out.append((im.strip(), par.strip()))
            break
    p = r'C:\sender\_ops\p25_user3_token.txt'
    if os.path.exists(p):
        lg = pw = ''
        for s in io.open(p, encoding='utf-8', errors='replace').read().split('\n'):
            m = re.match(r'\s*(?:логин|login)\s*[:=]\s*(\S.*)$', s, re.I)
            if m:
                lg = m.group(1).strip()
            m = re.match(r'\s*(?:пароль|password)\s*[:=]\s*(\S.*)$', s, re.I)
            if m:
                pw = m.group(1).strip()
        if lg and pw:
            out.append((lg, pw))
    return out


def dernut(put, im=None, par=None):
    rq = urllib.request.Request(PANEL + put)
    rq.add_header('User-Agent', 'progulka-3s')
    if im:
        rq.add_header('Authorization', 'Basic ' + base64.b64encode(
            ('%s:%s' % (im, par)).encode()).decode())
    try:
        with urllib.request.urlopen(rq, timeout=40) as o:
            telo = o.read().decode('utf-8', 'replace')
            return o.status, len(telo), bool(re.search(r'name="?password', telo, re.I))
    except urllib.error.HTTPError as e:
        return e.code, len(e.read()), False
    except Exception as e:  # noqa: BLE001
        return 0, 0, False


print('=== без входа')
for put in PUTI:
    kod, dl, forma = dernut(put)
    print('  %-30s код %-4s длина %-6d форма %s' % (put, kod, dl, forma))

for im, par in pary():
    print('\n=== логин %s' % im)
    voshli_gde = ''
    for put in PUTI:
        kod, dl, forma = dernut(put, im, par)
        priznak = 'ДАННЫЕ' if (kod == 200 and not forma and dl > 800) else (
            'форма' if forma else ('пусто/редирект' if kod in (200, 303, 307) else ''))
        print('  %-30s код %-4s длина %-6d %s' % (put, kod, dl, priznak))
        if priznak == 'ДАННЫЕ' and not voshli_gde:
            voshli_gde = put
    if voshli_gde:
        print('  -> ВХОД РАБОТАЕТ, данные на %s' % voshli_gde)
        print('ИТОГ ' + json.dumps({'рабочий логин': im, 'data-путь': voshli_gde},
                                   ensure_ascii=False))
        break
else:
    print('ИТОГ ' + json.dumps({'рабочий логин': None}, ensure_ascii=False))
