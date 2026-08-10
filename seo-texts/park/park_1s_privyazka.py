# -*- coding: utf-8 -*-
"""Чей ИНН на самом деле на карточке закупки — разбор подозрительных привязок.

Жребий вскрыл строку, где карточка 223-ФЗ «Запасные части к компрессорам для нужд филиала
ПАО "ОГК-2" — Адлерская ТЭС» висела на факте ПАО «ТГК-1». По такой строке продавец звонит не
туда. Масштаб посчитан по снимкам: на карточках 223-ФЗ ИНН заказчика печатается в 99 %
случаев, и 35 карточек из 2 569 показали ИНН, отличный от ИНН факта.

Прежде чем что-то править, надо УВИДЕТЬ, чей ИНН на странице: это может быть другое юрлицо
(ошибка привязки), а может быть головная компания того же холдинга или наоборот филиал —
тогда правка не нужна. Скрипт вытаскивает со страницы название заказчика и ВСЕ ИНН, кладёт
разбор на дроп целиком, а в stdout отдаёт только сводку (хвост stdout раннера обрезан).

Задание: C:\\sender\\_5ssylok.json (список {inn, tip, url}).
"""
import io, json, os, re, sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ZAD = r'C:\sender\_5ssylok.json'
DROP = r'C:\seostat\drop\drop-storage\PARK-1S-PRIVYAZKA-RAZBOR.json'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')
INN = re.compile(r'(?<!\d)(\d{10}|\d{12})(?!\d)')


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
    for z in zad:
        r = {'inn_fakta': z['inn'], 'tip': z.get('tip'), 'url': z['url']}
        try:
            for popytka in range(3):
                try:
                    otv = pg.goto(z['url'], timeout=90000, wait_until='domcontentloaded')
                    break
                except Exception:
                    if popytka == 2:
                        raise
                    pg.wait_for_timeout(4000 * (popytka + 1))
            pg.wait_for_timeout(2500)
            t = re.sub(r'\s+', ' ', pg.inner_text('body'))
            r['http'] = otv.status if otv else None
            zak = re.search(r'Заказчик\s+(.{0,120}?)(?:\s+Начальная|\s+Размещение|\s+Способ|$)', t)
            r['zakazchik'] = zak.group(1).strip() if zak else ''
            org = re.search(r'Организация, осуществляющая размещение\s+(.{0,120}?)(?:\s+Начальная|$)', t)
            r['razmeshchaet'] = org.group(1).strip() if org else ''
            r['inn_na_stranice'] = sorted(set(INN.findall(t)))[:6]
            r['sovpal'] = z['inn'] in r['inn_na_stranice']
            r['predmet'] = (re.search(r'Объект закупки\s+(.{0,140})', t) or
                            re.search(r'(.{0,140})', t)).group(1).strip()
        except Exception as e:  # noqa: BLE001
            r['oshibka'] = str(e)[:140]
        out.append(r)
    br.close()

with open(DROP + '.tmp', 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
    f.flush()
    os.fsync(f.fileno())
os.replace(DROP + '.tmp', DROP)

sovp = sum(1 for r in out if r.get('sovpal'))
pusto = sum(1 for r in out if not r.get('inn_na_stranice') and not r.get('oshibka'))
osh = sum(1 for r in out if r.get('oshibka'))
print('карточек разобрано: %d' % len(out))
print('  ИНН факта нашёлся на странице ......... %d' % sovp)
print('  на странице ВООБЩЕ нет ИНН ............ %d' % pusto)
print('  не открылась .......................... %d' % osh)
for r in out[:14]:
    print('  %s -> %s | заказчик: %s' % (r['inn_fakta'], ','.join(r.get('inn_na_stranice') or []) or '—',
                                          (r.get('zakazchik') or r.get('razmeshchaet') or '')[:46]))
print('полный разбор: PARK-1S-PRIVYAZKA-RAZBOR.json на дропе')
