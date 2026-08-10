# -*- coding: utf-8 -*-
"""Проверка ПАРЫ ссылок: одна должна показать машину, другая — ИНН.

Прежняя проверка открывала одну ссылку и требовала от неё всего сразу. Это давало заниженную
долю: ЕИС 44-ФЗ печатает название заказчика без ИНН, ЭТП ГПБ и Тендер.Про — тоже, и такие
факты выглядели недоказанными, хотя ИНН доказан второй ссылкой (карточка организации).

Здесь открываются обе, и вердикт складывается:
    машина названа  — на странице есть тип машины (по общему списку синонимов);
    ИНН напечатан   — на странице есть ИНН факта.
Если обе части закрыты, пусть даже разными страницами, факт доказан.

Задание: C:\\sender\\_zhrebiy_para.json — {fakt_id, inn, tip, url_mashina, url_inn}.
Полный разбор кладётся на дроп, в stdout — сводка (хвост stdout раннера обрезан).
"""
import io, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import park_sin

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ZAD = r'C:\sender\_zhrebiy_para.json'
RABOCHIY = r'C:\sender\park_zhrebiy_para.json'
DROP = r'C:\seostat\drop\drop-storage\PARK-1S-ZHREBIY-PARA.json'
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
from playwright.sync_api import sync_playwright

out = []
exe = hrom()
with sync_playwright() as p:
    kw = {'headless': True, 'args': ['--no-sandbox']}
    if exe:
        kw['executable_path'] = exe
    br = p.chromium.launch(**kw)
    pg = br.new_context(user_agent=UA, locale='ru-RU', ignore_https_errors=True).new_page()

    def otkryt(u):
        """-> (код, текст) с тремя заходами; пустой текст значит «страницу не дали»."""
        if not u:
            return None, ''
        for popytka in range(3):
            try:
                otv = pg.goto(u, timeout=90000, wait_until='domcontentloaded')
                pg.wait_for_timeout(2500)
                return (otv.status if otv else None), re.sub(r'\s+', ' ', pg.inner_text('body'))
            except Exception:
                if popytka == 2:
                    return None, ''
                pg.wait_for_timeout(4000 * (popytka + 1))
        return None, ''

    for z in zad:
        r = {k: z[k] for k in ('fakt_id', 'inn', 'tip', 'url_mashina', 'url_inn')}
        kod_m, t_m = otkryt(z['url_mashina'])
        # вторую страницу не открываем повторно, если это тот же адрес
        if z['url_inn'] and z['url_inn'] == z['url_mashina']:
            kod_i, t_i = kod_m, t_m
        else:
            kod_i, t_i = otkryt(z['url_inn'])
        r['http_mashina'], r['http_inn'] = kod_m, kod_i
        r['mashina_nazvana'] = bool(t_m) and park_sin.nazvana(z['tip'], t_m.lower())
        r['inn_napechatan'] = bool(t_i) and (z['inn'] in t_i)
        r['dokazano'] = bool(r['mashina_nazvana'] and r['inn_napechatan'])
        i = t_m.lower().find((park_sin.SIN.get(z['tip']) or [z['tip'][:9].lower()])[0])
        r['citata'] = t_m[max(0, i - 80):i + 140] if i >= 0 else t_m[:160]
        if not t_m:
            r['pochemu'] = 'страницу машины не дали'
        elif not r['mashina_nazvana']:
            r['pochemu'] = 'машина на странице не названа'
        elif not z['url_inn']:
            r['pochemu'] = 'ссылки на ИНН у факта нет'
        elif not t_i:
            r['pochemu'] = 'страницу с ИНН не дали'
        elif not r['inn_napechatan']:
            r['pochemu'] = 'ИНН на странице не напечатан'
        else:
            r['pochemu'] = ''
        out.append(r)
        with open(RABOCHIY, 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
    br.close()

import shutil
shutil.copyfile(RABOCHIY, DROP + '.tmp')
os.replace(DROP + '.tmp', DROP)
import collections
k = collections.Counter(r['pochemu'] or 'ДОКАЗАНО (машина и ИНН)' for r in out)
print('фактов в жребии: %d' % len(out))
for a, b in k.most_common():
    print('  %-40s %d' % (a, b))
print('ДОКАЗАНО: %d из %d' % (sum(1 for r in out if r['dokazano']), len(out)))
print('полный разбор: PARK-1S-ZHREBIY-PARA.json на дропе')
