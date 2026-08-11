# -*- coding: utf-8 -*-
"""Проверка МОЕГО же вердикта: правда ли 1 009 помеченных ссылок ничего не доказывают.

3-я сессия возразила по делу. Я пометил ссылки негодными по ВИДУ АДРЕСА (чужой идентификатор
в поле searchString), а браузером проверил всего две из них. Она тот же класс проверила
жребием и получила обратное: 32 поисковые ссылки из 34 доказывают — на отрисованной странице
стоит и предмет закупки, и слово машины. И предложила правило, которое снимает спор:

    поисковая ссылка считается доказательством, только если на ОТРИСОВАННОЙ странице
    стоит слово машины — не по виду адреса, а по тому, что видно.

Правило верное, и мой вердикт под ним нужно перепроверить, а не защищать. Здесь беру жребий
из помеченных `negodnaya` и открываю их браузером с сервера — тем же прибором, каким она
меряла свои.

Три исхода на ссылку:
    доказывает      — на странице есть слово машины (тип факта по общему списку синонимов);
    пусто           — страница открылась, машины нет (шапка ЕИС без результатов);
    не дали         — страницу не отдали вовсе.

Контроль: выдуманный запрос `searchString=щварцкопферъ` — прибор обязан сказать «машины нет».

Задание: C:\\sender\\_negodnye_proba.json — [{fakt_id, inn, tip, url, prichina}].
"""
import io, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import park_sin

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ZAD = r'C:\sender\_negodnye_proba.json'
DROP = r'C:\seostat\drop\drop-storage\PARK-1S-NEGODNYE-PROBA.json'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')
KONTROL = ('https://zakupki.gov.ru/epz/order/extendedsearch/results.html'
           '?searchString=%D1%89%D0%B2%D0%B0%D1%80%D1%86%D0%BA%D0%BE%D0%BF%D1%84%D0%B5%D1%80%D1%8A')


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
    proby = zad + [{'fakt_id': 0, 'inn': '', 'tip': 'компрессор', 'url': KONTROL,
                    'prichina': 'КОНТРОЛЬ'}]
    for z in proby:
        r = dict(z)
        t = ''
        for popytka in range(3):
            try:
                otv = pg.goto(z['url'], timeout=90000, wait_until='domcontentloaded')
                pg.wait_for_timeout(4500)   # выдачу рисует скрипт, ждём дольше
                r['http'] = otv.status if otv else None
                t = re.sub(r'\s+', ' ', pg.inner_text('body'))
                break
            except Exception as e:  # noqa: BLE001
                if popytka == 2:
                    r['oshibka'] = str(e)[:80]
                else:
                    pg.wait_for_timeout(4000 * (popytka + 1))
        r['znakov'] = len(t)
        r['mashina_nazvana'] = bool(t) and park_sin.nazvana(z['tip'], t.lower())
        # «ничего не найдено» ЕИС печатает прямым текстом — отличаем пустую выдачу от отказа
        r['pusto_yavno'] = bool(re.search(r'не найдено|нет данных|ничего не найдено', t, re.I))
        # ГЛАВНОЕ: связывает ли страница машину именно с НАШИМ предприятием
        r['inn_na_stranice'] = bool(z['inn']) and z['inn'] in t
        i = t.lower().find((park_sin.SIN.get(z['tip']) or [z['tip'][:9].lower()])[0])
        r['citata'] = t[max(0, i - 70):i + 130] if i >= 0 else t[:150]
        r['itog'] = ('не дали' if not t else
                     'пусто' if not r['mashina_nazvana'] else
                     'доказывает МАШИНУ У НАС' if r['inn_na_stranice'] else
                     'машина есть, НО ЧЬЯ — не сказано')
        out.append(r)
    br.close()

with open(r'C:\sender\park_negodnye_proba.json', 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False)
    f.flush()
    os.fsync(f.fileno())
import shutil
shutil.copyfile(r'C:\sender\park_negodnye_proba.json', DROP + '.tmp')
os.replace(DROP + '.tmp', DROP)

import collections
k = collections.Counter(r['itog'] for r in out if r['prichina'] != 'КОНТРОЛЬ')
print('проверено ссылок: %d' % (len(out) - 1))
for a, n in k.most_common():
    print('  %-14s %d' % (a, n))
kk = collections.Counter((r['prichina'][:34], r['itog']) for r in out if r['prichina'] != 'КОНТРОЛЬ')
print()
print('по причине пометки:')
for (pr, it), n in sorted(kk.items()):
    print('  %-36s %-12s %d' % (pr, it, n))
kontrol = [r for r in out if r['prichina'] == 'КОНТРОЛЬ'][0]
print()
print('КОНТРОЛЬ (выдуманное слово): %s, знаков %d' % (kontrol['itog'], kontrol['znakov']))
print('полный разбор: PARK-1S-NEGODNYE-PROBA.json на дропе')
