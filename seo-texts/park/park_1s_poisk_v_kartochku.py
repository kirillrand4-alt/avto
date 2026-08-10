# -*- coding: utf-8 -*-
"""Проверка правила «поиск по номеру -> карточка закупки» на ВЫБОРКЕ.

Повод: пятая ссылка жребия вела на `extendedsearch?searchString=0390100009419000169` —
номер полный, но страница поиска показывает 3 622 знака и ни ИНН, ни предмета: результаты
рисуются скриптом. Та же закупка по адресу карточки отдаёт 8 368 знаков с предметом и
заказчиком. Значит «поиск по полному номеру» я зря считал крепкой ссылкой.

Таких ссылок 14 467 — открывать каждую нельзя, поэтому правило проверяется НА ВЫБОРКЕ
в 60 штук, и в журнале это будет сказано прямо: правило проверено выборочно, а применено
ко всем. Признак годности: карточка отдаёт заметно больше текста и в нём есть номер.

Пишем в C:\\sender\\park_poisk_proba.jsonl с fsync.
"""
import json, os, re, sys, time

ZAD = r'C:\sender\_poisk_proba.json'
OUT = r'C:\sender\park_poisk_proba.jsonl'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')


def hrom():
    k = r'C:\sender\pw-browsers'
    if os.path.isdir(k):
        for d in sorted(os.listdir(k), reverse=True):
            e = os.path.join(k, d, 'chrome-win64', 'chrome.exe')
            if os.path.exists(e):
                return e


zad = json.load(open(ZAD, encoding='utf-8'))
gotovo = set()
if os.path.exists(OUT):
    for ln in open(OUT, encoding='utf-8', errors='replace'):
        try:
            gotovo.add(json.loads(ln)['rowid'])
        except Exception:
            pass
ochered = [z for z in zad if z['rowid'] not in gotovo]
itog = {'v_probe': len(zad), 'ranee': len(gotovo), 'v_vyzove': len(ochered),
        'kartochka_luchshe': 0, 'kartochka_pustaya': 0, 'oshibok': 0}
if not ochered:
    print(json.dumps(itog, ensure_ascii=False))
    sys.exit()

from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    kw = {'headless': True, 'args': ['--no-sandbox']}
    e = hrom()
    if e:
        kw['executable_path'] = e
    br = p.chromium.launch(**kw)
    pg = br.new_context(user_agent=UA, locale='ru-RU', ignore_https_errors=True).new_page()
    for z in ochered:
        nomer = z['novaya'].split('regNumber=')[-1]
        r = dict(z, ts=time.strftime('%Y-%m-%d %H:%M:%S'))
        try:
            otv = pg.goto(z['novaya'], timeout=70000, wait_until='domcontentloaded')
            pg.wait_for_timeout(1600)
            t = re.sub(r'\s+', ' ', pg.inner_text('body'))
            r['http'] = otv.status if otv else None
            r['znakov'] = len(t)
            r['nomer_na_stranice'] = nomer in t
            r['inn_na_stranice'] = z['inn'] in t
            i = t.find('Объект закупки')
            r['predmet'] = t[i:i + 160] if i >= 0 else ''
            if r['nomer_na_stranice'] and len(t) > 5000:
                r['verdikt'] = 'карточка отдаётся'
                itog['kartochka_luchshe'] += 1
            else:
                r['verdikt'] = 'карточка не лучше поиска'
                itog['kartochka_pustaya'] += 1
        except Exception as ex:
            r['verdikt'] = 'ошибка'
            r['oshibka'] = str(ex)[:130]
            itog['oshibok'] += 1
        with open(OUT, 'a', encoding='utf-8') as f:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
    br.close()
print(json.dumps(itog, ensure_ascii=False))
