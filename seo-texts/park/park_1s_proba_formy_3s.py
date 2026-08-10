# -*- coding: utf-8 -*-
"""Проверка формы 3-й сессии: доказывает ли поиск организации по ИНН что-нибудь.

Она дописала 9 141 факту ссылку `epz/organization/search/results.html?searchString=<ИНН>` и
проверила её пробой: «200, на странице видны И ИНН, И название». Мой прогон это подтвердил
формально — «ИНН в теле: true». Но ИНН стоит в самой строке запроса, и он же отражается в
поле поиска: страница может показывать ЭХО ЗАПРОСА, а не найденную организацию. Разница
принципиальная: в первом случае ссылка не доказывает ничего.

Проверяем по трём признакам сразу, для каждого ИНН:
  1) сколько раз ИНН встречается в тексте (эхо даёт один — в поле ввода);
  2) есть ли на странице НАЗВАНИЕ организации, которое мы уже знаем из карточки по коду;
  3) контроль: тот же запрос с заведомо несуществующим ИНН — если «ИНН в теле» истинно и
     там, значит признак меряет эхо, а не находку.
"""
import io, json, os, re, sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ZAD = r'C:\sender\_proba_formy.json'
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

exe = hrom()
out = []
with sync_playwright() as p:
    kw = {'headless': True, 'args': ['--no-sandbox']}
    if exe:
        kw['executable_path'] = exe
    br = p.chromium.launch(**kw)
    pg = br.new_context(user_agent=UA, locale='ru-RU', ignore_https_errors=True).new_page()
    for z in zad:
        u = ('https://zakupki.gov.ru/epz/organization/search/results.html?searchString='
             + z['inn'])
        r = {'inn': z['inn'], 'ждём_имя': (z.get('imya') or '')[:60]}
        try:
            otv = pg.goto(u, timeout=90000, wait_until='domcontentloaded')
            pg.wait_for_timeout(3000)
            t = re.sub(r'\s+', ' ', pg.inner_text('body'))
            r['http'] = otv.status if otv else None
            r['знаков'] = len(t)
            r['ИНН встречается раз'] = t.count(z['inn'])
            slova = [w for w in re.findall(r'[А-ЯЁA-Z]{4,}', (z.get('imya') or '').upper())][:3]
            r['слова имени на странице'] = [w for w in slova if w in t.upper()]
            r['есть блок результатов'] = bool(re.search(r'(?i)найдено|результат|организац', t))
            r['кусок'] = t[:200]
        except Exception as e:  # noqa: BLE001
            r['ошибка'] = str(e)[:140]
        out.append(r)
    br.close()
print(json.dumps(out, ensure_ascii=False, indent=1)[:5000])
