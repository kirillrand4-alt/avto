# -*- coding: utf-8 -*-
"""Проба канала РТС-тендер по форме, найденной 3-й сессией. Смотрю разметку, потом пишу сбор.

Её находка: код ответа 503, но страница РИСУЕТСЯ; и ИНН стоит прямо в адресе организатора
(`/poisk/organizator/<ИНН>-<КПП>/`). Прежде чем строить сборщик, надо увидеть своими
глазами, что именно отдаёт поиск и какие ссылки на странице есть.
"""
import json, os, re, sys, urllib.parse

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')


def hrom():
    k = r'C:\sender\pw-browsers'
    if os.path.isdir(k):
        for d in sorted(os.listdir(k), reverse=True):
            e = os.path.join(k, d, 'chrome-win64', 'chrome.exe')
            if os.path.exists(e):
                return e


slovo = sys.argv[1] if len(sys.argv) > 1 else 'компрессорная станция'
from playwright.sync_api import sync_playwright
o = {}
with sync_playwright() as p:
    kw = {'headless': True, 'args': ['--no-sandbox']}
    e = hrom()
    if e:
        kw['executable_path'] = e
    br = p.chromium.launch(**kw)
    pg = br.new_context(user_agent=UA, locale='ru-RU', ignore_https_errors=True).new_page()
    for imya, u in (
        ('поиск', 'https://www.rts-tender.ru/poisk/search?keywords=' + urllib.parse.quote(slovo)),
        ('поиск2', 'https://www.rts-tender.ru/poisk?keywords=' + urllib.parse.quote(slovo)),
    ):
        try:
            otv = pg.goto(u, timeout=90000, wait_until='domcontentloaded')
            # У РТС стоит Anti-DDoS-заслон: первая страница — заглушка «Проверяем ваш
            # браузер… перенаправление через 2». Мой первый заход ждал 3,5 с и прочёл
            # именно её (209 знаков) — прибор увидел бы «канал мёртв» там, где он живой.
            # Ждём, пока тело перестанет быть заглушкой, до 40 секунд.
            t = ''
            for _ in range(20):
                pg.wait_for_timeout(2000)
                t = re.sub(r'\s+', ' ', pg.inner_text('body'))
                if len(t) > 1500 and 'Проверяем ваш браузер' not in t:
                    break
            o.setdefault('_zaslon', {})[imya] = ('заглушка не ушла' if 'Проверяем ваш браузер' in t
                                                 else 'заслон пройден')
            ssyl = [a.get_attribute('href') or '' for a in pg.query_selector_all('a[href]')]
            org = [s for s in ssyl if '/organizator/' in s or '/comorganizers/' in s]
            proc = [s for s in ssyl if re.search(r'/poisk/id/\d+', s)]
            inny = sorted({m.group(1) for s in org for m in [re.search(r'/(\d{10})-\d+', s)] if m})
            o[imya] = {'url': u, 'http': otv.status if otv else None, 'знаков': len(t),
                       'слово в тексте': slovo.split()[0].lower() in t.lower(),
                       'ссылок всего': len(ssyl), 'организаторов': len(org),
                       'процедур': len(proc), 'ИНН из адресов': inny[:8],
                       'пример организатора': org[0] if org else '',
                       'пример процедуры': proc[0] if proc else '',
                       'начало текста': t[:220]}
        except Exception as ex:
            o[imya] = {'url': u, 'ошибка': str(ex)[:160]}
    br.close()
print(json.dumps(o, ensure_ascii=False, indent=1))
