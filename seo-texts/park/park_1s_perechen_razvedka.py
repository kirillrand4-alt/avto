# -*- coding: utf-8 -*-
"""Как устроен перечень заключений ЭПБ, прежде чем переводить 264 факта на карточки.

У этих фактов ссылка — `monitor-pb.ru/conclusions?exploiter=<ИНН>`: это ПЕРЕЧЕНЬ, он
показывает список заключений эксплуатанта, но конкретной машины не доказывает (в жребии
такая ссылка дважды вышла «ИНН на странице не найден»). Хочу заменить перечень на карточку
конкретного заключения — но сперва смотрю, что на странице перечня есть: адреса карточек,
наименования, заводские номера, постраничность.

Ничего не меняем: печатаем структуру одной страницы для двух ИНН.
"""
import io, json, os, re, sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')


def hrom():
    k = r'C:\sender\pw-browsers'
    if os.path.isdir(k):
        for d in sorted(os.listdir(k), reverse=True):
            e = os.path.join(k, d, 'chrome-win64', 'chrome.exe')
            if os.path.exists(e):
                return e


from playwright.sync_api import sync_playwright

exe = hrom()
out = {}
with sync_playwright() as p:
    kw = {'headless': True, 'args': ['--no-sandbox']}
    if exe:
        kw['executable_path'] = exe
    br = p.chromium.launch(**kw)
    pg = br.new_context(user_agent=UA, locale='ru-RU', ignore_https_errors=True).new_page()
    # Сверяем В ОДНОМ прогоне карточку и перечень: если карточка открывается, а перечень
    # нет — это не «сайт лёг», а именно путь /conclusions недоступен нам.
    for imya, u in (('карточка (контроль)', 'https://monitor-pb.ru/conclusion/66-%D0%A2%D0%A3-06699-2017'),
                    ('перечень 2614019198', 'https://monitor-pb.ru/conclusions?exploiter=2614019198'),
                    ('перечень без параметра', 'https://monitor-pb.ru/conclusions')):
        inn = '2614019198'
        r = {}
        try:
            otv = pg.goto(u, timeout=90000, wait_until='domcontentloaded')
            pg.wait_for_timeout(3000)
            r['http'] = otv.status if otv else None
            telo = pg.inner_text('body')
            r['знаков'] = len(telo)
            r['ИНН на странице'] = inn in telo
            ssylki = pg.eval_on_selector_all(
                'a[href*="/conclusion/"]',
                '''els => els.slice(0, 40).map(e => ({
                       href: e.getAttribute('href'),
                       txt: (e.innerText || '').slice(0, 60),
                       ryadom: (e.closest('tr') || e.parentElement).innerText.replace(/\\s+/g,' ').slice(0, 200)
                   }))''')
            r['карточек на странице'] = len(ssylki)
            r['примеры'] = ssylki[:5]
            r['есть постраничность'] = bool(re.search(r'(?i)страниц|показать ещё|далее', telo))
        except Exception as e:  # noqa: BLE001
            r['ошибка'] = str(e)[:180]
        out[imya] = r
    br.close()
print(json.dumps(out, ensure_ascii=False, indent=1)[:5500])
