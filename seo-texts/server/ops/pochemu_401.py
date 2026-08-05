# -*- coding: utf-8 -*-
"""Почему панели отвечают 401 — норма это или поломка.

Всю смену я печатал «8012 → 401, 8014 → 401» и читал это как «жива, просит
вход». Ни разу не проверил, ЧТО именно отвечает 401: страница входа обычно
отдаёт 200 с формой либо 302 на /login, а голый 401 бывает у HTTP Basic или у
API-заслона. Разница важна: если 401 отдаёт САМА страница входа, оператор в
панель не попадёт.
"""
import io, json, urllib.error, urllib.request

ПУТИ = ('/', '/login', '/vhod', '/health', '/api/health', '/static/style.css')
for порт in (8012, 8014):
    print(f'=== порт {порт}')
    for путь in ПУТИ:
        url = f'http://127.0.0.1:{порт}{путь}'
        try:
            о = urllib.request.urlopen(url, timeout=8)
            тело = о.read(300).decode('utf-8', 'replace')
            загл = dict(о.headers)
            print(f'   {путь:16} {о.getcode()}  тип={загл.get("Content-Type","?")[:24]:24} '
                  f'| {" ".join(тело.split())[:60]}')
        except urllib.error.HTTPError as e:
            тело = e.read(300).decode('utf-8', 'replace')
            wa = e.headers.get('WWW-Authenticate', '')
            loc = e.headers.get('Location', '')
            print(f'   {путь:16} {e.code}  WWW-Authenticate={wa[:24]!r} '
                  f'Location={loc[:30]!r} | {" ".join(тело.split())[:60]}')
        except Exception as e:
            print(f'   {путь:16} НЕ ОТКРЫЛСЯ {type(e).__name__}: {str(e)[:50]}')
