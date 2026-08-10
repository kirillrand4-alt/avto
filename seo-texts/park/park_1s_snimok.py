# -*- coding: utf-8 -*-
"""Снимок страницы панели глазами, а не флагами.

Владелец судит о виде по картинке, и проверять вид набором `'centro.css' in text`
недостаточно: подключить стиль и всё равно выглядеть чужим — легко. Здесь страница
открывается настоящим входом и снимается целиком; файл уходит на дроп.
"""
import json, os, re, sys, urllib.parse

B = 'http://127.0.0.1:8012/obzvon'
PUT = sys.argv[1] if len(sys.argv) > 1 else '/centro/park/7736050003'
IMYA = sys.argv[2] if len(sys.argv) > 2 else 'park-snimok-kartochki.png'
PW = ''
if os.path.exists(r'C:\sender\centro-user3.txt'):
    t = open(r'C:\sender\centro-user3.txt', encoding='utf-8', errors='replace').read()
    m = re.search(r'(?:пароль|password)\s*[:=]\s*(\S+)', t, re.I)
    PW = m.group(1) if m else t.strip().split()[-1]


def hrom():
    k = r'C:\sender\pw-browsers'
    if os.path.isdir(k):
        for d in sorted(os.listdir(k), reverse=True):
            e = os.path.join(k, d, 'chrome-win64', 'chrome.exe')
            if os.path.exists(e):
                return e


from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    kw = {'headless': True, 'args': ['--no-sandbox']}
    e = hrom()
    if e:
        kw['executable_path'] = e
    br = p.chromium.launch(**kw)
    ctx = br.new_context(viewport={'width': 1500, 'height': 1000}, locale='ru-RU')
    pg = ctx.new_page()
    # Вход делаем ЗАПРОСОМ, а не кликом: у формы входа кнопка без type="submit",
    # и клик по селектору отваливался таймаутом. Форма — обычный POST, request.post
    # проходит через тот же контекст и оставляет куку.
    pg.goto(B + '/centro/login', timeout=60000)
    ctx.request.post(B + '/centro/login',
                     form={'username': 'user3', 'password': PW})
    pg.wait_for_timeout(500)
    # `networkidle` перестал срабатывать, как только в карточке появились снимки
    # доказательств: картинки грузятся лениво, и сеть не «затихает». Ждём разметку
    # и даём фиксированную паузу.
    pg.goto(B + PUT, timeout=90000, wait_until='domcontentloaded')
    pg.wait_for_timeout(3000)
    fayl = os.path.join(r'C:\sender', IMYA)
    # ТОЛЬКО ЭКРАН по третьему аргументу: карточка с фактами вытянулась на 7 000 точек,
    # и на такой картинке шапку не разглядеть.
    polnaya = not (len(sys.argv) > 3 and sys.argv[3] == 'ekran')
    pg.screenshot(path=fayl, full_page=polnaya)
    print(json.dumps({'put': PUT, 'fayl': fayl, 'baytov': os.path.getsize(fayl),
                      'zagolovok': pg.title()}, ensure_ascii=False))
    br.close()
