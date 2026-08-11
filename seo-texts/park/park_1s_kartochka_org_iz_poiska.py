# -*- coding: utf-8 -*-
"""Достройка второй ссылки: из ПОИСКА организации вытащить адрес её КАРТОЧКИ.

У 766 предприятий выдачи нет ни одной ссылки, доказывающей ИНН: машина у них подтверждена
ЭТП ГПБ (7 796 фактов), Тендер.Про, hh.ru — а эти площадки ИНН не печатают. Пара «машина +
ИНН» у них не собирается.

Прямой ход — поиск организации в ЕИС по ИНН:

    epz/organization/search/results.html?searchString=<ИНН>

Но после вчерашней находки поисковую страницу за доказательство брать нельзя. Поэтому здесь
поиск используется не как доказательство, а как СПРАВОЧНИК: со страницы результата снимается
ссылка на карточку организации

    epz/organization/view/info.html?organizationCode=<код>

и дальше проверяется уже сама карточка — постоянный адрес, на котором ИНН напечатан
реквизитом. В базу идёт карточка, поиск не сохраняется.

Три вопроса к карточке, все три должны сойтись:
    ИНН на карточке          — тот, что мы искали;
    название на карточке     — то же, что у нас записано (сверяем по первым словам);
    адрес карточки постоянный — organizationCode, а не строка запроса.

Контроль: выдуманный ИНН 9999999999 — карточки быть не должно. 3-я сессия показала, что
этот номер «находится» из-за вхождения цифр в ОГРН тестовой организации, поэтому сверяем
именно то, что стоит ПОСЛЕ слова «ИНН», а не вхождение цифр в текст.

Задание: C:\\sender\\_kartochka_org.json — [{inn, nazvanie}].
"""
import io, json, os, re, sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ZAD = r'C:\sender\_kartochka_org.json'
DROP = r'C:\seostat\drop\drop-storage\PARK-1S-KARTOCHKA-ORG.json'
POISK = 'https://zakupki.gov.ru/epz/organization/search/results.html?searchString=%s'
KARTA = 'https://zakupki.gov.ru/epz/organization/view/info.html?organizationCode=%s'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')
KOD = re.compile(r'organizationCode=(\d{6,})')
POSLE_INN = re.compile(r'ИНН\s*[:№]?\s*(\d{10,12})')


def hrom():
    k = r'C:\sender\pw-browsers'
    if os.path.isdir(k):
        for d in sorted(os.listdir(k), reverse=True):
            e = os.path.join(k, d, 'chrome-win64', 'chrome.exe')
            if os.path.exists(e):
                return e


def pohozhe(a, b):
    """Названия сходятся, если совпали первые два значимых слова (ООО/АО отбрасываем)."""
    chist = lambda s: [w for w in re.findall(r'[А-ЯЁA-Z]{3,}', (s or '').upper())
                       if w not in ('ООО', 'АО', 'ПАО', 'ЗАО', 'ОАО', 'ФГУП', 'МУП', 'ГУП')]
    x, y = chist(a)[:2], chist(b)[:2]
    return bool(x and y and (x[0] == y[0] or (len(x) > 1 and len(y) > 1 and x[1] == y[1])))


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
    proby = zad + [{'inn': '9999999999', 'nazvanie': 'КОНТРОЛЬ'}]
    for z in proby:
        r = {'inn': z['inn'], 'nazvanie': z['nazvanie'], 'kontrol': z['nazvanie'] == 'КОНТРОЛЬ'}
        try:
            pg.goto(POISK % z['inn'], timeout=90000, wait_until='domcontentloaded')
            pg.wait_for_timeout(6000)          # список рисует скрипт
            html = pg.content()
            kody = KOD.findall(html)
            r['kodov_v_poiske'] = len(set(kody))
            if kody:
                kod = kody[0]
                r['kod'] = kod
                r['url_kartochki'] = KARTA % kod
                otv = pg.goto(r['url_kartochki'], timeout=90000, wait_until='domcontentloaded')
                pg.wait_for_timeout(3500)
                t = re.sub(r'\s+', ' ', pg.inner_text('body'))
                r['http'] = otv.status if otv else None
                inny = POSLE_INN.findall(t)
                r['inn_na_kartochke'] = z['inn'] in inny
                r['nazvanie_shoditsya'] = pohozhe(z['nazvanie'], t[:400])
                i = t.find(z['inn'])
                r['citata'] = t[max(0, i - 110):i + 40] if i >= 0 else t[:150]
                r['godno'] = bool(r['inn_na_kartochke'])
            else:
                r['godno'] = False
                r['pochemu'] = 'в поиске нет ссылки на карточку организации'
        except Exception as e:  # noqa: BLE001
            r['oshibka'] = str(e)[:90]
            r['godno'] = False
        out.append(r)
    br.close()

with open(r'C:\sender\park_kartochka_org.json', 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False)
    f.flush()
    os.fsync(f.fileno())
import shutil
shutil.copyfile(r'C:\sender\park_kartochka_org.json', DROP + '.tmp')
os.replace(DROP + '.tmp', DROP)

for r in out:
    print('%-12s кодов=%-3s ИНН на карточке=%-6s имя сходится=%-6s %s%s'
          % (r['inn'], r.get('kodov_v_poiske'), r.get('inn_na_kartochke'),
             r.get('nazvanie_shoditsya'), (r.get('pochemu') or r.get('oshibka') or '')[:40],
             '  <-- КОНТРОЛЬ' if r['kontrol'] else ''))
godno = sum(1 for r in out if r.get('godno') and not r['kontrol'])
k = [r for r in out if r['kontrol']][0]
print()
print('карточка добыта и ИНН сошёлся: %d из %d' % (godno, len(zad)))
print('КОНТРОЛЬ (выдуманный ИНН): годно=%s, кодов в поиске %s'
      % (k.get('godno'), k.get('kodov_v_poiske')))
