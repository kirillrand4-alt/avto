# -*- coding: utf-8 -*-
"""Куда переехал API Портала поставщиков: адреса берутся из его же JS, а не угадываются.

ПОВОД. Домен с сервера отвечает 200, но `api/Cssp/Purchase/Query` теперь отдаёт HTML-оболочку
SPA, а не JSON. Значит площадка жива, а путь сменился — и перебирать пути наугад можно
долго. Правильный вход: скачать бандл приложения и вынуть из него строки, начинающиеся на
`/api/`; фронтенд обязан знать свои же адреса.
"""
import json
import re
import urllib.parse
import urllib.request

BAZA = 'https://zakupki.mos.ru'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')


def vzyat(u, tajm=45):
    req = urllib.request.Request(u, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=tajm) as r:
        return r.status, r.read().decode('utf-8', 'replace')


st, glav = vzyat(BAZA + '/')
skripty = re.findall(r'src="([^"]+\.js)"', glav)
print(f'главная: HTTP {st}, скриптов в разметке {len(skripty)}')
puti = set()
for s in skripty[:8]:
    u = s if s.startswith('http') else BAZA + '/' + s.lstrip('/')
    try:
        _, js = vzyat(u, 90)
    except Exception as e:  # noqa: BLE001
        print(f'  {u[-40:]}: {type(e).__name__}')
        continue
    naydeno = set(re.findall(r'["\'`](/?api/[A-Za-z0-9_/\-{}$.]{4,80})["\'`]', js))
    puti |= naydeno
    print(f'  {u[-46:]}: {len(js)} байт, путей api/ {len(naydeno)}')
print(f'\nвсего разных путей api/: {len(puti)}')
interes = sorted(p for p in puti if re.search(r'purchase|tender|auction|need|offer|cssp|query|search', p, re.I))
for p in interes[:60]:
    print('  ', p)

# Проверка живых кандидатов: GET без параметров, лишь бы отличить JSON от оболочки SPA.
print('\nпроверка кандидатов:')
for p in interes[:14]:
    u = BAZA + ('/' + p.lstrip('/'))
    if '{' in u or '$' in u:
        continue
    try:
        st, telo = vzyat(u, 30)
        vid = 'JSON' if telo.lstrip()[:1] in '{[' else ('оболочка SPA' if '<!doctype' in telo[:60].lower() else 'иное')
        print(f'  {st} {vid:<14} {p}  {telo[:90].replace(chr(10), " ")!r}')
    except Exception as e:  # noqa: BLE001
        print(f'  --- {type(e).__name__} {str(e)[:60]:<40} {p}')
