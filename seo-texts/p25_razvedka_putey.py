# -*- coding: utf-8 -*-
"""Разведка настоящих путей панели: где живая карточка с людьми (ct-person).

/obzvon/centro/list дал 404 — этих путей нет. Карточка, которую я чинила
(centro_card.html), обслуживается роутером routes_centro с адресом /centro{n} — то есть
база в URL это centro1, centro2 (с цифрой), а не centro. Перебираю кандидатов без входа
и с кредами из .env, печатаю код, длину, форму и есть ли на странице ct-card/ct-person.
Пароли не печатаю.
"""
import base64
import io
import json
import os
import re
import urllib.error
import urllib.request

PANEL = 'http://127.0.0.1:8012'
BAZY = ['centro', 'centro1', 'centro2', 'centro3', 'centro4', 'centro5']
HVOSTY = ['', '/card?skip=0', '/list?page=1', '?skip=0&view=card']


def para_iz_env():
    for env in (r'C:\seostat\.env', r'C:\seostat\app\.env'):
        if os.path.exists(env):
            for s in io.open(env, encoding='utf-8', errors='replace').read().split('\n'):
                m = re.match(r'\s*obzvon_users\s*=\s*(.+)$', s, re.I)
                if m:
                    for para in m.group(1).strip().strip('"\'').split(','):
                        if ':' in para:
                            im, _, par = para.strip().partition(':')
                            return im.strip(), par.strip()
    return '', ''


def dernut(put, im=None, par=None):
    rq = urllib.request.Request(PANEL + put)
    rq.add_header('User-Agent', 'progulka-3s')
    if im:
        rq.add_header('Authorization', 'Basic ' + base64.b64encode(
            ('%s:%s' % (im, par)).encode()).decode())
    try:
        with urllib.request.urlopen(rq, timeout=40) as o:
            t = o.read().decode('utf-8', 'replace')
            return o.status, len(t), ('ct-person' in t or 'ct-card' in t or
                                      'Люди с должностями' in t), \
                bool(re.search(r'name="?password', t, re.I))
    except urllib.error.HTTPError as e:
        return e.code, len(e.read() or b''), False, False
    except Exception as ex:  # noqa: BLE001
        return 0, 0, False, False


im, par = para_iz_env()
print('=== без входа')
zhiv = []
for b in BAZY:
    for h in HVOSTY:
        put = '/obzvon/%s%s' % (b, h)
        kod, dl, karta, forma = dernut(put)
        if kod not in (404,):
            print('  %-30s код %-4s длина %-6d карточка %s форма %s'
                  % (put, kod, dl, 'ДА' if karta else '-', 'да' if forma else '-'))
        if karta:
            zhiv.append(put)

print('\n=== с логином %s (из .env)' % (im or '—'))
zhiv2 = []
if im:
    for b in BAZY:
        for h in HVOSTY:
            put = '/obzvon/%s%s' % (b, h)
            kod, dl, karta, forma = dernut(put, im, par)
            if kod not in (404,) and (karta or dl > 800 or kod != 200):
                print('  %-30s код %-4s длина %-6d карточка %s форма %s'
                      % (put, kod, dl, 'ДА' if karta else '-', 'да' if forma else '-'))
            if karta and not forma:
                zhiv2.append(put)

print('ИТОГ ' + json.dumps({'карточка без входа': zhiv[:6],
                            'карточка с входом': zhiv2[:6],
                            'логин из env': im or None}, ensure_ascii=False))
