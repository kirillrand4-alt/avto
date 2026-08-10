# -*- coding: utf-8 -*-
"""Пятая просьба владельца: открыть случайные ссылки-доказательства и посмотреть, куда ведут.

Открываем браузером на сервере (из контейнера ЕИС и monitor-pb недоступны) и печатаем
ровно то, что нужно для суждения ГЛАЗАМИ, а не «200 OK»:
   * код ответа и длину тела — 200 с шапкой портала это не доказательство;
   * есть ли на странице ИНН предприятия;
   * есть ли слово типа машины и модель;
   * окно текста вокруг найденного — цитату видно, спорить не о чем.

Задание: C:\\sender\\_5ssylok.json (список {inn,tip,model,url,vid}).
"""
import json, os, re, sys

ZAD = r'C:\sender\_5ssylok.json'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')


def hrom():
    k = r'C:\sender\pw-browsers'
    if os.path.isdir(k):
        for d in sorted(os.listdir(k), reverse=True):
            e = os.path.join(k, d, 'chrome-win64', 'chrome.exe')
            if os.path.exists(e):
                return e
    return None


zad = json.load(open(ZAD, encoding='utf-8'))
from playwright.sync_api import sync_playwright
exe = hrom()
out = []
with sync_playwright() as p:
    kw = {'headless': True, 'args': ['--no-sandbox']}
    if exe:
        kw['executable_path'] = exe
    br = p.chromium.launch(**kw)
    pg = br.new_context(user_agent=UA, locale='ru-RU', ignore_https_errors=True).new_page()
    for z in zad:
        r = {'inn': z['inn'], 'tip': z['tip'], 'model': z.get('model', ''),
             'vid': z.get('vid', ''), 'url': z['url']}
        try:
            otv = pg.goto(z['url'], timeout=90000, wait_until='domcontentloaded')
            pg.wait_for_timeout(2500)
            t = re.sub(r'\s+', ' ', pg.inner_text('body'))
            r['http'] = otv.status if otv else None
            r['знаков'] = len(t)
            r['ИНН на странице'] = z['inn'] in t
            slovo = z['tip'].split()[0].lower()[:9]
            i = t.lower().find(slovo)
            r['тип на странице'] = i >= 0
            r['цитата тип'] = t[max(0, i - 90):i + 150] if i >= 0 else ''
            if z.get('model'):
                j = t.lower().find(z['model'].lower())
                r['модель на странице'] = j >= 0
                r['цитата модель'] = t[max(0, j - 90):j + 120] if j >= 0 else ''
            k = t.find(z['inn'])
            r['цитата ИНН'] = t[max(0, k - 110):k + 110] if k >= 0 else ''
        except Exception as e:
            r['ошибка'] = str(e)[:160]
        out.append(r)
    br.close()
print(json.dumps(out, ensure_ascii=False, indent=1))
