# -*- coding: utf-8 -*-
"""Какой хост и какой метод у API портала: GET на все пути отдаёт оболочку SPA.

ПОВОД. Пути `/api/...` в бандле есть, но GET по каждому возвращает HTML-оболочку с кодом
200. Два объяснения, и оба проверяемы: либо API живёт на ДРУГОМ хосте (в бандле прописан
базовый адрес), либо эти ручки принимают только POST, а на GET срабатывает catch-all
маршрут SPA. Проверяю оба, а не выбираю по вкусу.
"""
import json
import re
import urllib.parse
import urllib.request

BAZA = 'https://zakupki.mos.ru'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')


def vzyat(u, tajm=60, dannye=None, zagolovki=None):
    h = {'User-Agent': UA, 'Accept': 'application/json'}
    h.update(zagolovki or {})
    req = urllib.request.Request(u, headers=h, data=dannye,
                                 method='POST' if dannye is not None else 'GET')
    try:
        with urllib.request.urlopen(req, timeout=tajm) as r:
            return r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')


_, glav = vzyat(BAZA + '/')
skripty = [s for s in re.findall(r'src="([^"]+\.js)"', glav)]
hosty, prefiksy = set(), set()
for s in skripty[:8]:
    u = s if s.startswith('http') else BAZA + '/' + s.lstrip('/')
    try:
        _, js = vzyat(u, 90)
    except Exception:  # noqa: BLE001
        continue
    hosty |= set(re.findall(r'https://([a-z0-9.\-]*mos\.ru)', js))
    prefiksy |= set(re.findall(r'["\'`]((?:https?://[a-z0-9.\-]+)?/?(?:newapi|api|gateway|backend)[a-z0-9/_\-]{0,20})/?["\'`,]', js, re.I))
print('хосты *.mos.ru в бандле:', sorted(hosty)[:20])
print('возможные префиксы API:', sorted(p for p in prefiksy if len(p) < 40)[:25])

PUT = '/api/Cssp/Purchase/Query'
dto = {'filter': {'nameLike': 'центробежный компрессор'}, 'skip': 0, 'take': 3}
telo = json.dumps(dto, ensure_ascii=False).encode()

print('\nпопытки:')
proby = [('GET  zakupki', BAZA + PUT + '?queryDto=' + urllib.parse.quote(json.dumps(dto, ensure_ascii=False)), None)]
for h in sorted(hosty):
    if h != 'zakupki.mos.ru':
        proby.append((f'GET  {h}', f'https://{h}{PUT}?queryDto=' + urllib.parse.quote(json.dumps(dto, ensure_ascii=False)), None))
proby.append(('POST zakupki', BAZA + PUT, telo))
proby.append(('POST old', 'https://old.zakupki.mos.ru' + PUT, telo))
for imya, u, d in proby:
    try:
        st, t = vzyat(u, 40, dannye=d, zagolovki={'Content-Type': 'application/json'} if d else None)
        vid = 'JSON' if t.lstrip()[:1] in '{[' else ('оболочка SPA' if '<!doctype' in t[:60].lower() else 'иное')
        print(f'  {imya:<22} {st} {vid:<14} {t[:120].replace(chr(10), " ")!r}')
    except Exception as e:  # noqa: BLE001
        print(f'  {imya:<22} --- {type(e).__name__}: {str(e)[:80]}')
