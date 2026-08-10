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


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import park_sin  # синонимы типа машины — один список на все проверки

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
            # ПОВТОР ПРИ ОБРЫВЕ. Замер 10.08 в 20:2x: из 20 ссылок 11 не открылись
            # (7 таймаутов monitor-pb, 4 обрыва на других), потому что параллельно шла
            # моя же съёмка доказательств и мы упёрлись в частоту. Один заход по ссылке
            # даёт не долю доказанности, а долю шума; три захода с паузой отделяют
            # «страница не доказывает» от «нам не дали страницу».
            otv = None
            for popytka in range(3):
                try:
                    otv = pg.goto(z['url'], timeout=90000, wait_until='domcontentloaded')
                    break
                except Exception:
                    if popytka == 2:
                        raise
                    pg.wait_for_timeout(4000 * (popytka + 1))
            r['попыток'] = popytka + 1
            pg.wait_for_timeout(2500)
            t = re.sub(r'\s+', ' ', pg.inner_text('body'))
            r['http'] = otv.status if otv else None
            r['знаков'] = len(t)
            r['ИНН на странице'] = z['inn'] in t
            # МАШИНУ ИЩЕМ ПО СИНОНИМАМ, а не по каноническому слову: в записи ЭПБ ОАО «РЖД»
            # стоит «воздухосборник В-10 зав. № 216-73», а тип у факта — «ресивер». Прежний
            # поиск в лоб записывал такую страницу как «тип не найден» и занижал доказанность.
            nizh = t.lower()
            slova = park_sin.SIN.get(z['tip']) or [z['tip'].split()[0].lower()[:9]]
            i, slovo = -1, ''
            for s in slova:
                j = nizh.find(s)
                if j >= 0 and (i < 0 or j < i):
                    i, slovo = j, s
            r['тип на странице'] = i >= 0
            r['каким словом'] = slovo
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
# ПОЛНЫЙ ответ — в хранилище дропа, в stdout — только сводка строками.
# Раннер отдаёт лишь ХВОСТ stdout (6 000 знаков): на пяти ссылках это проходило, на
# двадцати обрезало середину, и замер читать было нечем.
DROP = r'C:\seostat\drop\drop-storage\PARK-1S-SSYLKI-PROVERKA.json'
with open(DROP + '.tmp', 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
    f.flush()
    os.fsync(f.fileno())
os.replace(DROP + '.tmp', DROP)
dok = 0
for i, r in enumerate(out, 1):
    est = bool(r.get('ИНН на странице')) and bool(r.get('тип на странице'))
    dok += 1 if est else 0
    print('%2d %s %-12s %-16s http=%-4s знаков=%-6s %s' % (
        i, 'ДА ' if est else 'нет', r.get('inn', ''), (r.get('tip') or '')[:16],
        r.get('http'), r.get('знаков'), (r.get('url') or '')[:58]))
print('ДОКАЗЫВАЮТ ПОЛНОСТЬЮ (ИНН и машина на странице): %d из %d' % (dok, len(out)))
print('полный разбор с цитатами: PARK-1S-SSYLKI-PROVERKA.json на дропе')
