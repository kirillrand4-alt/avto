# -*- coding: utf-8 -*-
"""Почему POST входа в панель отдаёт 503, хотя GET той же страницы отдаёт 200.

Это не мелочь: если вход действительно сломан, владелец не откроет ни обзвон, ни карточки
парка. Смотрим, КТО отвечает (заголовок Server), что в теле и одинаково ли ведут себя
локальный порт приложения и внешний адрес.
"""
import io, json, sys, urllib.error, urllib.parse, urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
TELO = urllib.parse.urlencode({'username': 'user3', 'password': 'заведомо-неверный'}).encode()
o = {}
for imya, url in (('локально 8012', 'http://127.0.0.1:8012/obzvon/centro/login'),
                  ('через сайт', 'https://parsercompressor.online/obzvon/centro/login')):
    for sposob, dannye in (('GET', None), ('POST', TELO)):
        klyuch = '%s %s' % (imya, sposob)
        try:
            req = urllib.request.Request(url, data=dannye)
            if dannye:
                req.add_header('Content-Type', 'application/x-www-form-urlencoded')
            with urllib.request.urlopen(req, timeout=45) as r:
                b = r.read().decode('utf-8', 'replace')
                o[klyuch] = {'http': r.status, 'server': r.headers.get('Server'),
                             'знаков': len(b), 'начало': b[:120].replace('\n', ' ')}
        except urllib.error.HTTPError as e:
            b = e.read().decode('utf-8', 'replace')
            o[klyuch] = {'http': e.code, 'server': e.headers.get('Server'),
                         'знаков': len(b), 'начало': b[:200].replace('\n', ' ')}
        except Exception as e:  # noqa: BLE001
            o[klyuch] = str(e)[:160]
print(json.dumps(o, ensure_ascii=False, indent=1))
