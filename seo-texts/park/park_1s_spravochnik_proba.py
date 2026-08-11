# -*- coding: utf-8 -*-
"""Проба: годится ли публичный справочник как ВТОРАЯ ссылка (доказать ИНН+название).

Реестр организаций ЕИС для 766 наших предприятий пуст — «Поиск не дал результатов»: они
закупали на коммерческих площадках и в 44/223-ФЗ не значатся. Нужен другой постоянный адрес,
где ИНН и название стоят рядом. Пробую публичные карточки трёх справочников.

Требование к годной ссылке прежнее и строгое: на странице должны быть ОБА — наш ИНН
(после слова «ИНН», а не просто вхождение цифр) и название, похожее на наше.
Контроль — выдуманный ИНН: карточки быть не должно.
"""
import io, os, re, sys, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
PROBY = [('7813026343', 'ЭКОМЕТ-С'), ('7705907626', 'РИМЕРА-СЕРВИС'),
         ('5501072598', 'РМЗ ГПН-ОНПЗ'), ('9999999999', 'КОНТРОЛЬ')]
FORMY = [('checko', 'https://checko.ru/company/%s'),
         ('rusprofile', 'https://www.rusprofile.ru/search?query=%s'),
         ('list-org', 'https://www.list-org.com/search?type=inn&val=%s')]
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')
POSLE_INN = re.compile(r'ИНН\s*[:№]?\s*(\d{10,12})')
def hrom():
    k = r'C:\sender\pw-browsers'
    if os.path.isdir(k):
        for d in sorted(os.listdir(k), reverse=True):
            e = os.path.join(k, d, 'chrome-win64', 'chrome.exe')
            if os.path.exists(e): return e
from playwright.sync_api import sync_playwright
out = []
with sync_playwright() as p:
    kw = {'headless': True, 'args': ['--no-sandbox']}
    e = hrom()
    if e: kw['executable_path'] = e
    br = p.chromium.launch(**kw)
    pg = br.new_context(user_agent=UA, locale='ru-RU', ignore_https_errors=True).new_page()
    for imya, shablon in FORMY:
        for inn, nazv in PROBY:
            r = {'spravochnik': imya, 'inn': inn, 'kontrol': nazv == 'КОНТРОЛЬ'}
            try:
                otv = pg.goto(shablon % inn, timeout=45000, wait_until='domcontentloaded')
                pg.wait_for_timeout(3000)
                t = re.sub(r'\s+', ' ', pg.inner_text('body'))
                r['http'] = otv.status if otv else None
                r['znakov'] = len(t)
                r['inn_posle_slova'] = inn in POSLE_INN.findall(t)
                r['imya_est'] = nazv != 'КОНТРОЛЬ' and bool(re.search(
                    re.escape(nazv.split()[0][:7]), t, re.I))
            except Exception as ex:  # noqa: BLE001
                r['oshibka'] = str(ex)[:60]
            out.append(r)
    br.close()
for r in out:
    print('%-11s %-12s http=%-5s знаков=%-7s ИНН после слова=%-6s имя=%-6s%s'
          % (r['spravochnik'], r['inn'], r.get('http'), r.get('znakov'),
             r.get('inn_posle_slova'), r.get('imya_est'),
             '  <-- КОНТРОЛЬ' if r['kontrol'] else ''))
print()
for imya, _ in FORMY:
    svoi = [r for r in out if r['spravochnik'] == imya]
    god = sum(1 for r in svoi if not r['kontrol'] and r.get('inn_posle_slova') and r.get('imya_est'))
    k = [r for r in svoi if r['kontrol']][0]
    print('%-12s годно %d из 3, контроль ИНН-после-слова=%s' % (imya, god, k.get('inn_posle_slova')))
