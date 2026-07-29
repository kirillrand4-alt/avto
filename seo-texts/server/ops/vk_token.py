# -*- coding: utf-8 -*-
"""Токен VK для СЕРВЕРНЫХ вызовов, без дельфина. Инструкция: ../VK-AUTH.md

Почему так: нынешний VK_TOKEN_USER выдан в браузере (Implicit Flow) и привязан
к IP профиля дельфина 829115401 — прокси у него протух, и VK-путь встал.
Authorization Code Flow обменивает код на токен ЗАПРОСОМ С СЕРВЕРА, поэтому
токен работает с серверного IP, а с scope=offline ещё и бессрочен.

    python vk_token.py url                 — ссылка для разового входа владельца
    python vk_token.py exchange <code>     — обмен кода на токен + проверка + запись
    python vk_token.py check               — чем ходим сейчас и работает ли
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request

PANEL_ENV = r'C:\sender\panel.env'
REDIRECT = 'https://oauth.vk.com/blank.html'
API_V = '5.199'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')
# прямой опенер: туннель/прокси панели тут не нужен, нам важен именно
# СЕРВЕРНЫЙ IP — к нему VK и привяжет токен
_OP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def env(имя, по_умолчанию=''):
    v = os.environ.get(имя)
    if v:
        return v
    try:
        with open(PANEL_ENV, encoding='utf-8-sig') as f:
            for ln in f:
                ln = ln.strip()
                if ln and not ln.startswith('#') and '=' in ln:
                    k, _, val = ln.partition('=')
                    if k.strip() == имя:
                        return re.sub(r'\s+#.*$', '', val).strip()
    except OSError:
        pass
    return по_умолчанию


def запись_env(пары):
    """Дописать/заменить строки в panel.env, не трогая остальное."""
    строки = []
    try:
        with open(PANEL_ENV, encoding='utf-8-sig') as f:
            строки = f.read().splitlines()
    except OSError:
        pass
    for k, v in пары.items():
        нашли = False
        for i, ln in enumerate(строки):
            if ln.strip().startswith(k + '='):
                строки[i] = f'{k}={v}'
                нашли = True
                break
        if not нашли:
            строки.append(f'{k}={v}')
    with open(PANEL_ENV, 'w', encoding='utf-8') as f:
        f.write('\n'.join(строки) + '\n')


def _get(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    return json.loads(_OP.open(req, timeout=25).read())


def вызов(method, token, **prm):
    prm.update(access_token=token, v=API_V)
    return _get(f'https://api.vk.com/method/{method}?'
                + urllib.parse.urlencode(prm))


def cmd_url():
    app = env('VK_APP_ID')
    if not app:
        print(json.dumps({'итог': 'нет VK_APP_ID в panel.env — см. VK-AUTH.md, шаг 1'},
                         ensure_ascii=False))
        return
    # scope=offline это приложение НЕ принимает («invalid scope», проверено
    # 29.07): у приложений нового поколения VK его убрал. Поэтому просим только
    # groups; токен будет срочный, срок печатаем при обмене.
    # Переопределяется VK_SCOPE, если понадобится другой набор прав.
    u = ('https://oauth.vk.com/authorize?' + urllib.parse.urlencode({
        'client_id': app, 'display': 'page', 'redirect_uri': REDIRECT,
        'scope': env('VK_SCOPE', 'groups'), 'response_type': 'code', 'v': API_V}))
    print(json.dumps({
        'откройте_в_своём_браузере': u,
        'что_дальше': 'после входа адресная строка станет '
                      'https://oauth.vk.com/blank.html?code=XXXX — пришлите XXXX',
        'внимание': 'код живёт около минуты и одноразовый'}, ensure_ascii=False))


def cmd_exchange(code):
    app, sec = env('VK_APP_ID'), env('VK_APP_SECRET')
    if not (app and sec):
        print(json.dumps({'итог': 'нужны VK_APP_ID и VK_APP_SECRET в panel.env'},
                         ensure_ascii=False))
        return
    try:
        d = _get('https://oauth.vk.com/access_token?' + urllib.parse.urlencode({
            'client_id': app, 'client_secret': sec,
            'redirect_uri': REDIRECT, 'code': code}))
    except Exception as ex:  # noqa: BLE001
        print(json.dumps({'итог': f'обмен не удался: {type(ex).__name__}: {str(ex)[:160]}',
                          'подсказка': 'код одноразовый и живёт ~минуту — получите новый'},
                         ensure_ascii=False))
        return
    tok = d.get('access_token')
    if not tok:
        print(json.dumps({'итог': 'VK не отдал токен', 'ответ': d}, ensure_ascii=False))
        return
    # ПРОВЕРЯЕМ ДО ЗАПИСИ: токен, который не ходит с серверного IP, писать незачем
    проба = вызов('groups.search', tok, q='Северсталь', count=1, type='group')
    ok = bool((проба or {}).get('response'))
    жив = d.get('expires_in')
    итог = {'токен_получен': True, 'истекает_через_сек': жив,
            'бессрочный': жив in (0, None),
            'срок': ('бессрочный' if жив in (0, None)
                     else f'~{round((жив or 0) / 3600)} ч — потребуется обновление'),
            'refresh_token_есть': bool(d.get('refresh_token')),
            'groups.search_с_сервера': 'работает' if ok else проба}
    if ok:
        пары = {'VK_TOKEN_USER': tok, 'VK_USE_DOLPHIN': '0'}
        # refresh_token отдаёт VK ID; сохраняем, если пришёл — им обновляют
        # срочный токен без повторного входа владельца
        if d.get('refresh_token'):
            пары['VK_REFRESH_TOKEN'] = d['refresh_token']
        запись_env(пары)
        итог['записано_в_panel_env'] = ['VK_TOKEN_USER', 'VK_USE_DOLPHIN=0']
        итог['дельфин_для_vk'] = 'больше не нужен'
    else:
        итог['НЕ_записан'] = 'вызов с серверного IP не прошёл — см. ответ выше'
    print(json.dumps(итог, ensure_ascii=False))


def cmd_check():
    out = {'VK_USE_DOLPHIN': env('VK_USE_DOLPHIN', '(не задан → путь через дельфин)')}
    for имя in ('VK_TOKEN_USER', 'VK_TOKEN', 'VK_SERVICE_TOKEN'):
        tok = env(имя)
        if not tok:
            out[имя] = 'нет'
            continue
        рез = {}
        for метод, prm in (('groups.search', {'q': 'Северсталь', 'count': 1, 'type': 'group'}),
                           ('groups.getById', {'group_id': 'severstal'})):
            try:
                d = вызов(метод, tok, **prm)
                рез[метод] = ('ок' if d.get('response') is not None
                              else (d.get('error') or {}).get('error_msg', '?')[:70])
            except Exception as ex:  # noqa: BLE001
                рез[метод] = f'{type(ex).__name__}: {str(ex)[:60]}'
        out[имя] = рез
    print(json.dumps(out, ensure_ascii=False))


def main():
    к = sys.argv[1] if len(sys.argv) > 1 else 'check'
    if к == 'url':
        cmd_url()
    elif к == 'exchange' and len(sys.argv) > 2:
        cmd_exchange(sys.argv[2])
    else:
        cmd_check()


if __name__ == '__main__':
    main()
