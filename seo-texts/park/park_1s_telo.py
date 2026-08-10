# -*- coding: utf-8 -*-
"""Печатает НАЧАЛО ТЕЛА страницы по адресу из argv — чтобы судить глазами, а не по флагу.
Заведено после проверки пяти случайных ссылок: у tender.pro признаки «ИНН/тип/модель на
странице» дали False, и нужно увидеть, что там вообще лежит, прежде чем объявлять ссылку
негодной."""
import re, sys, os
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')
def hrom():
    k = r'C:\sender\pw-browsers'
    if os.path.isdir(k):
        for d in sorted(os.listdir(k), reverse=True):
            e = os.path.join(k, d, 'chrome-win64', 'chrome.exe')
            if os.path.exists(e): return e
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    kw = {'headless': True, 'args': ['--no-sandbox']}
    e = hrom()
    if e: kw['executable_path'] = e
    br = p.chromium.launch(**kw)
    pg = br.new_context(user_agent=UA, locale='ru-RU', ignore_https_errors=True).new_page()
    for u in sys.argv[1:]:
        try:
            r = pg.goto(u, timeout=90000, wait_until='domcontentloaded')
            pg.wait_for_timeout(2500)
            t = re.sub(r'\s+', ' ', pg.inner_text('body'))
            print('=== %s  http=%s  знаков=%d' % (u[:110], r.status if r else '?', len(t)))
            print(t[:1500])
        except Exception as ex:
            print('=== %s ОШИБКА %s' % (u[:110], str(ex)[:150]))
    br.close()
