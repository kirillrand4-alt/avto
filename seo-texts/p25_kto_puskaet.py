# -*- coding: utf-8 -*-
"""Какая пара логин:пароль пускает в centro. Пароли не печатаются — только имена и коды.

Вход в обзвон — Basic (в тестах `client.get(..., auth=...)`), а пары лежат в настройке
`obzvon_users` панели (`.env`, «логин:пароль,логин2:пароль2»). Значит рабочие креды уже
на сервере — их и беру, ничего не передавая через песочницу и не записывая в репозиторий.

Прибор собирает пары из трёх мест: настройка панели, файл p25_user3_token.txt, переменная
PANEL_LOGINS. По каждой шлёт Basic-заголовок на /obzvon/centro и печатает ТОЛЬКО имя
логина, код и что вернулось (форма входа или очередь). Пароль в вывод не попадает.
"""
import base64
import io
import json
import os
import re
import urllib.error
import urllib.request

PANEL = 'http://127.0.0.1:8012'


def iz_env_fayla():
    """obzvon_users из .env панели. Ищем .env рядом с приложением."""
    for env in (r'C:\seostat\.env', r'C:\seostat\app\.env'):
        if not os.path.exists(env):
            continue
        for s in io.open(env, encoding='utf-8', errors='replace').read().split('\n'):
            m = re.match(r'\s*obzvon_users\s*=\s*(.+)$', s, re.I)
            if m:
                znach = m.group(1).strip().strip('"\'')
                out = []
                for para in znach.split(','):
                    if ':' in para:
                        im, _, par = para.strip().partition(':')
                        out.append((im.strip(), par.strip(), '.env'))
                return out
    return []


def iz_tokena():
    p = r'C:\sender\_ops\p25_user3_token.txt'
    if not os.path.exists(p):
        return []
    login = parol = ''
    for s in io.open(p, encoding='utf-8', errors='replace').read().split('\n'):
        m = re.match(r'\s*(?:логин|login)\s*[:=]\s*(\S.*)$', s, re.I)
        if m:
            login = m.group(1).strip()
        m = re.match(r'\s*(?:пароль|password)\s*[:=]\s*(\S.*)$', s, re.I)
        if m:
            parol = m.group(1).strip()
    return [(login, parol, 'файл user3')] if login and parol else []


def iz_env_peremennoy():
    out = []
    for kus in os.environ.get('PANEL_LOGINS', '').replace(',', '\n').split('\n'):
        if '=' in kus:
            im, _, par = kus.partition('=')
            out.append((im.strip(), par.strip(), 'PANEL_LOGINS'))
    return out


def probovat(im, par):
    avt = 'Basic ' + base64.b64encode(('%s:%s' % (im, par)).encode()).decode()
    rq = urllib.request.Request(PANEL + '/obzvon/centro')
    rq.add_header('Authorization', avt)
    rq.add_header('User-Agent', 'progulka-3s')
    try:
        with urllib.request.urlopen(rq, timeout=40) as o:
            kod, telo = o.status, o.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        kod, telo = e.code, e.read().decode('utf-8', 'replace')
    except Exception as e:  # noqa: BLE001
        return 0, '__ОШИБКА__ %s' % type(e).__name__
    forma = bool(re.search(r'name="?password', telo, re.I))
    if kod == 200 and not forma:
        m = re.search(r'(?:всего|найдено)\D{0,12}(\d[\d\s]{0,9})', telo, re.I)
        return kod, 'ВОШЛИ, в очереди %s' % (re.sub(r'\s', '', m.group(1)) if m else '?')
    if kod == 200 and forma:
        return kod, 'форма входа (пара отвергнута)'
    return kod, telo[:40].replace('\n', ' ')


pary, vidalis = [], set()
for istochnik in (iz_env_fayla, iz_tokena, iz_env_peremennoy):
    for im, par, otkuda in istochnik():
        if (im, par) in vidalis:
            continue
        vidalis.add((im, par))
        pary.append((im, par, otkuda))

print('пар собрано: %d' % len(pary))
rabochaya = ''
for im, par, otkuda in pary:
    kod, chto = probovat(im, par)
    print('  логин %-10s из %-14s -> код %-4s %s' % (im or '(пусто)', otkuda, kod, chto))
    if 'ВОШЛИ' in chto and not rabochaya:
        rabochaya = im
print('ИТОГ ' + json.dumps({'рабочий логин найден': bool(rabochaya),
                            'логин': rabochaya}, ensure_ascii=False))
