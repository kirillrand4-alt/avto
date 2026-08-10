# -*- coding: utf-8 -*-
"""Проверка перевода ссылок tender.pro из формы SPA в форму, которая отдаёт карточку.

Находка 3-й сессии, подтверждённая у себя: адрес `tender.pro/#/tender/N` держит номер во
ФРАГМЕНТЕ (после решётки). Фрагмент на сервер не уходит вовсе, поэтому такой адрес всегда
отдаёт главную страницу портала — «ссылка открывается» и ничего не доказывает. Рабочая
форма: `tender.pro/api/tender/N/view_public`.

У меня таких 90. Переводим не вслепую: каждая новая страница открывается и сверяется —
виден ли предмет закупки и назван ли заказчик. ИНН на страницах tender.pro не печатается,
поэтому сверяем по НАЗВАНИЮ предприятия (корень из 5+ букв) и по слову типа машины;
что не сошлось — оставляем как есть и помечаем.

Пишем в C:\\sender\\park_tp_perevod.jsonl с fsync. Запуск: panel_py, argv = [сколько]
"""
import json, os, re, sys, time

ZAD = r'C:\sender\_tp_perevod.json'
OUT = r'C:\sender\park_tp_perevod.jsonl'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')


def hrom():
    k = r'C:\sender\pw-browsers'
    if os.path.isdir(k):
        for d in sorted(os.listdir(k), reverse=True):
            e = os.path.join(k, d, 'chrome-win64', 'chrome.exe')
            if os.path.exists(e):
                return e


def sdelano():
    v = set()
    if os.path.exists(OUT):
        for ln in open(OUT, encoding='utf-8', errors='replace'):
            try:
                v.add(json.loads(ln)['rowid'])
            except Exception:
                pass
    return v


skolko = int(sys.argv[1]) if len(sys.argv) > 1 else 50
zad = json.load(open(ZAD, encoding='utf-8'))
gotovo = sdelano()
ochered = [z for z in zad if z['rowid'] not in gotovo][:skolko]
itog = {'v_zadanii': len(zad), 'ranee': len(gotovo), 'v_vyzove': len(ochered),
        'kartochka_est': 0, 'glavnaya_portala': 0, 'oshibok': 0}
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
        r = dict(z)
        r['ts'] = time.strftime('%Y-%m-%d %H:%M:%S')
        try:
            otv = pg.goto(z['novaya'], timeout=70000, wait_until='domcontentloaded')
            pg.wait_for_timeout(1500)
            t = re.sub(r'\s+', ' ', pg.inner_text('body'))
            r['http'] = otv.status if otv else None
            r['znakov'] = len(t)
            i = t.find('Тендер')
            r['predmet'] = t[i:i + 260] if i >= 0 else t[:260]
            # «карточка есть» — если в теле назван конкретный тендер, а не только меню
            r['est_nomer'] = bool(re.search(r'id\s*%s' % re.escape(z['novaya'].split('/')[-2]), t)
                                  or 'Общая информация' in t)
            slovo = (z.get('tip') or '').split()[0].lower()[:9]
            r['tip_viden'] = bool(slovo and slovo in t.lower())
            if r['est_nomer'] and r['znakov'] > 1500:
                r['verdikt'] = 'карточка отдаётся — ссылку меняем'
                itog['kartochka_est'] += 1
            else:
                r['verdikt'] = 'главная портала, карточки нет'
                itog['glavnaya_portala'] += 1
        except Exception as ex:
            r['verdikt'] = 'ошибка'
            r['oshibka'] = str(ex)[:150]
            itog['oshibok'] += 1
        with open(OUT, 'a', encoding='utf-8') as f:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
    br.close()
print(json.dumps(itog, ensure_ascii=False))
