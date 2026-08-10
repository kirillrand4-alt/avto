# -*- coding: utf-8 -*-
"""Спор о том, печатается ли ИНН на странице поиска организаций ЕИС — меряю у себя.

3-я сессия показала снимками: на `organization/search?searchString=<ИНН>` в карточке
результата стоит строка реквизитов «ОГРН … ИНН … КПП …», то есть ИНН печатается. Мой
прошлый замер тем же браузером дал «ИНН встречается 1 раз» — как эхо в поле ввода. Значит
кто-то из нас смотрел на неотрисованную страницу.

Проверяю на ЕЁ примере и на МОЁМ, с длинной паузой и явным поиском шаблона «ИНН <цифры>»:
если после ожидания карточка появляется, прав сосед и мой замер был снят рано.

Заодно её находка: выдуманный 9999999999 «находится», потому что эти цифры входят в ОГРН
тестовой организации. Значит проверять надо не вхождение цифр, а то, что стоит ПОСЛЕ слова
«ИНН» — это тоже меряем.
"""
import io, json, os, re, sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')
PARY = [('её пример', '7424024375'), ('мой пример', '6315909640'),
        ('контроль', '9999999999')]
POSLE_INN = re.compile(r'ИНН\s*[:№]?\s*(\d{10,12})')


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
    pg = br.new_context(user_agent=UA, locale='ru-RU', ignore_https_errors=True).new_page()
    for imya, inn in PARY:
        u = ('https://zakupki.gov.ru/epz/organization/search/results.html?searchString=' + inn)
        r = {'кто': imya, 'inn': inn}
        try:
            otv = pg.goto(u, timeout=90000, wait_until='domcontentloaded')
            # ЖДЁМ ДОЛЬШЕ: список рисуется скриптом, на 2,5 с он мог не успеть
            pg.wait_for_timeout(9000)
            t = re.sub(r'\s+', ' ', pg.inner_text('body'))
            r['http'] = otv.status if otv else None
            r['знаков'] = len(t)
            r['цифры ИНН в тексте раз'] = t.count(inn)
            r['после слова ИНН стоят'] = POSLE_INN.findall(t)[:5]
            r['наш ИНН стоит после слова ИНН'] = inn in POSLE_INN.findall(t)
            r['кусок вокруг слова ИНН'] = ''
            m = re.search(r'.{0,80}ИНН\s*[:№]?\s*\d{10,12}.{0,60}', t)
            if m:
                r['кусок вокруг слова ИНН'] = m.group(0)
        except Exception as e:  # noqa: BLE001
            r['ошибка'] = str(e)[:140]
        out.append(r)
    br.close()
print(json.dumps(out, ensure_ascii=False, indent=1)[:4000])
