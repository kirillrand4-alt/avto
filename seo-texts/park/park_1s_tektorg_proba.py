# -*- coding: utf-8 -*-
"""Проба: можно ли починить 705 подделанных ссылок настоящей карточкой ТЭК-Торга.

Все 705 фактов, что держатся ТОЛЬКО на поисковой странице, пришли из одного источника —
`atlas_copco.db/tenders`. И ссылка у них устроена так:

    https://zakupki.gov.ru/epz/order/extendedsearch/results.html?searchString=tek_908858

`tek_908858` — это ВНУТРЕННИЙ идентификатор ТЭК-Торга, подставленный в поиск ЕИС. Сборщик
склеил чужой ID с адресом чужой площадки. Ссылка ведёт на живой домен, отдаёт http 200 — и
не докажет ничего никогда, потому что ЕИС такого номера не знает. Это хуже пустой ссылки:
пустую видно, а эта выглядит доказательством.

Здесь проверяю, можно ли вместо неё поставить настоящую. Из песочницы ТЭК-Торг отвечает 307
на самого себя (защита проверкой cookie), поэтому проба идёт с сервера браузером — 3-я
сессия ходит туда именно так.

Пробую четыре формы адреса на пяти идентификаторах и смотрю, что реально на той странице:
назван ли предмет закупки и напечатан ли ИНН заказчика.
"""
import io, json, os, re, sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ZAD = r'C:\sender\_tektorg_proba.json'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')
FORMY = ['https://www.tektorg.ru/procedures/%s',
         'https://www.tektorg.ru/procedures/view/%s',
         'https://www.tektorg.ru/procedures?searchText=%s',
         'https://www.tektorg.ru/procedures?name=%s']


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
    # контроль: выдуманный идентификатор не должен ничего находить
    proby = zad + [{'nomer': '999999999', 'inn': '0000000000', 'predmet': 'КОНТРОЛЬ'}]
    for z in proby:
        for shablon in FORMY:
            u = shablon % z['nomer']
            r = {'nomer': z['nomer'], 'inn': z['inn'], 'forma': shablon, 'url': u,
                 'kontrol': z['predmet'] == 'КОНТРОЛЬ'}
            try:
                otv = pg.goto(u, timeout=60000, wait_until='domcontentloaded')
                pg.wait_for_timeout(3500)
                t = re.sub(r'\s+', ' ', pg.inner_text('body'))
                r['http'] = otv.status if otv else None
                r['znakov'] = len(t)
                r['nomer_na_stranice'] = z['nomer'] in t
                r['inn_na_stranice'] = z['inn'] in t
                r['mashina_nazvana'] = bool(re.search(r'компрессор|atlas', t, re.I))
                i = t.lower().find('компрессор')
                r['citata'] = t[max(0, i - 70):i + 130] if i >= 0 else t[:130]
            except Exception as e:  # noqa: BLE001
                r['oshibka'] = str(e)[:90]
            out.append(r)
            if r.get('nomer_na_stranice'):
                break        # форма найдена, остальные не пробуем
    br.close()

with open(r'C:\sender\park_tektorg_proba.json', 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False)
    f.flush()
    os.fsync(f.fileno())
import shutil
D = r'C:\seostat\drop\drop-storage\PARK-1S-TEKTORG-PROBA.json'
shutil.copyfile(r'C:\sender\park_tektorg_proba.json', D + '.tmp')
os.replace(D + '.tmp', D)
for r in out:
    print('%-11s %-46s http=%-5s номер=%-5s ИНН=%-5s машина=%s%s'
          % (r['nomer'], r['forma'].split('tektorg.ru')[1][:46], r.get('http'),
             r.get('nomer_na_stranice'), r.get('inn_na_stranice'), r.get('mashina_nazvana'),
             '  <-- КОНТРОЛЬ' if r['kontrol'] else ''))
nashli = sum(1 for r in out if r.get('nomer_na_stranice') and not r['kontrol'])
kontrol = [r for r in out if r['kontrol']]
print()
print('карточка найдена: %d из %d идентификаторов' % (nashli, len(zad)))
print('контроль (выдуманный номер): найден на %d страницах из %d'
      % (sum(1 for r in kontrol if r.get('nomer_na_stranice')), len(kontrol)))
