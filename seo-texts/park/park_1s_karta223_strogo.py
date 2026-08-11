# -*- coding: utf-8 -*-
"""Строгая проверка карточки организации 223-ФЗ: ИНН должен стоять ПОСЛЕ слова «ИНН».

Мой общий прибор оценил эти ссылки вопросом «названа ли машина» и выдал «пусто» 12 из 12.
Вопрос был неверный: карточка ОРГАНИЗАЦИИ машину не называет и не обязана — она доказывает
ИНН. Чуть не пометил 5 985 годных ссылок негодными.

Здесь спрашиваю то, что эта ссылка и должна доказывать:
    ИНН стоит после слова «ИНН» (а не просто цифры где-то в тексте или в адресе);
    название организации на странице есть.
Контроль — выдуманный ИНН: карточки быть не должно.
"""
import io, json, os, re, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ZAD = r'C:\sender\_negodnye_proba.json'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')
POSLE = re.compile(r'ИНН\s*[:№]?\s*(\d{10,12})')
KONTROL = ('https://zakupki.gov.ru/epz/organization/view223/info.html'
           '?&inn=9999999999&kpp=999999999&ogrn=9999999999999')
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
    for z in zad + [{'inn': '9999999999', 'url': KONTROL, 'prichina': 'КОНТРОЛЬ'}]:
        r = {'inn': z['inn'], 'kontrol': z['prichina'] == 'КОНТРОЛЬ'}
        try:
            otv = pg.goto(z['url'], timeout=60000, wait_until='domcontentloaded')
            pg.wait_for_timeout(4000)
            t = re.sub(r'\s+', ' ', pg.inner_text('body'))
            r['http'] = otv.status if otv else None
            r['znakov'] = len(t)
            nashli = POSLE.findall(t)
            r['inn_posle_slova'] = z['inn'] in nashli
            # ЛОВУШКА: страница печатает ИНН из АДРЕСА (?inn=...), даже когда организации нет.
            # Контроль 9999999999 дал «ИНН после слова = True» на пустой странице.
            # Настоящую карточку отличают РЕКВИЗИТЫ, которых у пустой нет.
            r['ogrn_est'] = bool(re.search(r'ОГРН\s*[:№]?\s*\d{13,15}', t))
            r['mesto_est'] = 'Местонахождение' in t
            r['dokazano'] = bool(r['inn_posle_slova'] and r['ogrn_est'] and r['mesto_est'])
            r['vsego_inn_na_stranice'] = len(set(nashli))
            i = t.find(z['inn'])
            r['citata'] = t[max(0, i - 120):i + 40] if i >= 0 else t[:120]
        except Exception as ex:  # noqa: BLE001
            r['oshibka'] = str(ex)[:60]
        out.append(r)
    br.close()
for r in out:
    print('%-12s знаков=%-6s ИНН-после-слова=%-6s ОГРН=%-6s Местонахождение=%-6s ДОКАЗАНО=%-6s%s'
          % (r['inn'], r.get('znakov'), r.get('inn_posle_slova'), r.get('ogrn_est'),
             r.get('mesto_est'), r.get('dokazano'), '  <-- КОНТРОЛЬ' if r['kontrol'] else ''))
god = sum(1 for r in out if not r['kontrol'] and r.get('dokazano'))
k = [r for r in out if r['kontrol']][0]
print()
print('ИНН доказан карточкой: %d из %d' % (god, len(zad)))
print('КОНТРОЛЬ: ИНН-после-слова=%s (эхо адреса!), ДОКАЗАНО=%s, знаков %s'
      % (k.get('inn_posle_slova'), k.get('dokazano'), k.get('znakov')))
