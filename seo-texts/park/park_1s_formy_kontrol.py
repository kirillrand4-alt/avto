# -*- coding: utf-8 -*-
"""Сверка числа 3-й сессии: правда ли «17 карточек» — это список по умолчанию.

Она написала: `?searchText=` и `?q=` на ТЭК-Торге отдают 17 карточек и на настоящем слове,
и на выдуманном, и вообще без параметра — значит параметр игнорируется, а 17 это просто
первая страница списка. Меряю тем же вопросом, но своим прибором: сравниваю ДЛИНУ ТЕКСТА
страницы, а не число карточек (длину прибор считает сам, без разбора вёрстки).
"""
import io, json, os, re, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
B = 'https://www.tektorg.ru/procedures'
PROBY = [('?name= настоящее', B + '?name=компрессор'),
         ('?name= КОНТРОЛЬ', B + '?name=щварцкопферъ'),
         ('?searchText= настоящее', B + '?searchText=компрессор'),
         ('?searchText= КОНТРОЛЬ', B + '?searchText=щварцкопферъ'),
         ('?q= настоящее', B + '?q=компрессор'),
         ('?q= КОНТРОЛЬ', B + '?q=щварцкопферъ'),
         ('БЕЗ ПАРАМЕТРА', B)]


def hrom():
    k = r'C:\sender\pw-browsers'
    if os.path.isdir(k):
        for d in sorted(os.listdir(k), reverse=True):
            e = os.path.join(k, d, 'chrome-win64', 'chrome.exe')
            if os.path.exists(e):
                return e


from playwright.sync_api import sync_playwright
out = []
exe = hrom()
with sync_playwright() as p:
    kw = {'headless': True, 'args': ['--no-sandbox']}
    if exe:
        kw['executable_path'] = exe
    br = p.chromium.launch(**kw)
    pg = br.new_context(locale='ru-RU', ignore_https_errors=True).new_page()
    for imya, u in PROBY:
        r = {'proba': imya, 'url': u}
        try:
            otv = pg.goto(u, timeout=60000, wait_until='domcontentloaded')
            pg.wait_for_timeout(4000)
            t = re.sub(r'\s+', ' ', pg.inner_text('body'))
            r['http'] = otv.status if otv else None
            r['znakov'] = len(t)
            r['slovo_est'] = bool(re.search(r'компрессор', t, re.I))
        except Exception as e:  # noqa: BLE001
            r['oshibka'] = str(e)[:70]
        out.append(r)
    br.close()
for r in out:
    print('%-24s http=%-5s знаков=%-7s слово «компрессор» на странице=%s'
          % (r['proba'], r.get('http'), r.get('znakov'), r.get('slovo_est')))
d = {r['proba']: r.get('znakov') for r in out}
print()
print('ВЫВОД: ?searchText= и ?q= совпадают с «без параметра»: %s'
      % (d.get('?searchText= настоящее') == d.get('?q= настоящее') == d.get('БЕЗ ПАРАМЕТРА')))
print('       ?name= на контроле короче, чем на настоящем слове: %s'
      % (d.get('?name= КОНТРОЛЬ', 0) < d.get('?name= настоящее', 0)))
