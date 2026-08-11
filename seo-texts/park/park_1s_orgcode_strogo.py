# -*- coding: utf-8 -*-
"""Третья форма карточки организации: ?organizationCode=<код>. Проверка с СВОИМ контролем.

3-я сессия дала поправку к моему же правилу, и она точна: **контроль обязан подделывать ТО ЖЕ,
что несёт адрес**. Мой прежний контроль подделывал ИНН — это верно для формы `?inn=…`, где
ИНН и есть содержимое запроса (страница печатала его обратно даже для выдуманного). Для её
формы `?agencyId=…` подделывать надо agencyId, потому что ИНН в адресе нет вовсе.

У меня нашлась третья форма, которую я строгим признаком ещё не мерил:

    ссылок view223 с ?inn=          5985   (проверено, эхо-дефект пойман)
    ссылок с ?agencyId=                0   (форма 3-й сессии, у меня отсутствует)
    ссылок с ?organizationCode=     6700   ← эти
    
Здесь адрес несёт КОД организации, а не ИНН. Значит:
    вопрос   — печатает ли карточка наш ИНН (после слова «ИНН») и реквизиты;
    контроль — выдуманный organizationCode, а не выдуманный ИНН.
Если у выдуманного кода карточка окажется «доказанной», признак ложный и здесь.
"""
import io, json, os, re, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ZAD = r'C:\sender\_orgcode_proba.json'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')
POSLE = re.compile(r'ИНН\s*[:№]?\s*(\d{10,12})')
KONTROL = 'https://zakupki.gov.ru/epz/organization/view/info.html?organizationCode=99999999999999999999'
def hrom():
    k = r'C:\sender\pw-browsers'
    if os.path.isdir(k):
        for d in sorted(os.listdir(k), reverse=True):
            e = os.path.join(k, d, 'chrome-win64', 'chrome.exe')
            if os.path.exists(e): return e
zad = json.load(open(ZAD, encoding='utf-8'))
from playwright.sync_api import sync_playwright
out = []
with sync_playwright() as p:
    kw = {'headless': True, 'args': ['--no-sandbox']}
    e = hrom()
    if e: kw['executable_path'] = e
    br = p.chromium.launch(**kw)
    pg = br.new_context(user_agent=UA, locale='ru-RU', ignore_https_errors=True).new_page()
    for z in zad + [{'inn': '0000000000', 'url': KONTROL, 'kontrol': True}]:
        r = {'inn': z['inn'], 'kontrol': bool(z.get('kontrol'))}
        try:
            otv = pg.goto(z['url'], timeout=60000, wait_until='domcontentloaded')
            pg.wait_for_timeout(3500)
            t = re.sub(r'\s+', ' ', pg.inner_text('body'))
            r['http'] = otv.status if otv else None
            r['znakov'] = len(t)
            r['inn_posle_slova'] = z['inn'] in POSLE.findall(t)
            r['ogrn'] = bool(re.search(r'ОГРН\s*[:№]?\s*\d{13,15}', t))
            r['mesto'] = 'Местонахождение' in t
            r['dokazano'] = bool(r['inn_posle_slova'] and r['ogrn'] and r['mesto'])
        except Exception as ex:  # noqa: BLE001
            r['oshibka'] = str(ex)[:70]
        out.append(r)
    br.close()
for r in out:
    print('%-12s znakov=%-6s inn=%-6s ogrn=%-6s mesto=%-6s DOKAZANO=%-6s%s'
          % (r['inn'], r.get('znakov'), r.get('inn_posle_slova'), r.get('ogrn'),
             r.get('mesto'), r.get('dokazano'), '  <-- KONTROL' if r['kontrol'] else ''))
g = sum(1 for r in out if not r['kontrol'] and r.get('dokazano'))
k = [r for r in out if r['kontrol']][0]
print()
print('DOKAZANO %d iz %d' % (g, len(zad)))
print('KONTROL vydumannyy organizationCode: dokazano=%s, znakov=%s' % (k.get('dokazano'), k.get('znakov')))
