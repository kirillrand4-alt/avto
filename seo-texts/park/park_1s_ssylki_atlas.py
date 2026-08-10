# -*- coding: utf-8 -*-
"""Возврат ссылок 442 фактам, у которых их нет вовсе.

Откуда взялись: 290 пришли из старой базы `atlas_copco.db`, где хранился ТЕКСТ закупки без
адреса, остальные — из резолва ИНН, тоже без адреса. Все они помечены
`karantin='нет ссылки-доказательства'` и не выдаются как доказанные, но по правилу
владельца «каждый факт доказывается ссылкой» это долг, а не норма.

Способ: ищем в ЕИС по ТОЧНОЙ фразе из `chto_naydeno` (это название закупки), берём первую
карточку, открываем её и подтверждаем двумя признаками сразу — ИНН заказчика на карточке
и совпадение названия закупки. Ссылка ставится только при обоих совпадениях; иначе факт
остаётся без ссылки и это видно.

Пишем в C:\\sender\\park_atlas_ssylki.jsonl с fsync, резюм по fakt_id.
Запуск: panel_py, argv = [<сколько фактов за вызов>]
"""
import json, os, re, sys, time, urllib.parse

ZAD = r'C:\sender\_atlas_bez_ssylki.json'
OUT = r'C:\sender\park_atlas_ssylki.jsonl'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')
POISK = ('https://zakupki.gov.ru/epz/order/extendedsearch/results.html'
         '?fz44=on&fz223=on&recordsPerPage=_50&searchString=')


def hrom():
    k = r'C:\sender\pw-browsers'
    if os.path.isdir(k):
        for d in sorted(os.listdir(k), reverse=True):
            e = os.path.join(k, d, 'chrome-win64', 'chrome.exe')
            if os.path.exists(e):
                return e


def sdelano():
    v = set()
    if os.path.exists(OUT):
        for ln in open(OUT, encoding='utf-8', errors='replace'):
            try:
                v.add(json.loads(ln)['fakt_id'])
            except Exception:
                pass
    return v


def slova(t):
    return set(re.findall(r'[а-яёa-z0-9]{4,}', (t or '').lower()))


skolko = int(sys.argv[1]) if len(sys.argv) > 1 else 60
zad = json.load(open(ZAD, encoding='utf-8'))
gotovo = sdelano()
ochered = [z for z in zad if z['fakt_id'] not in gotovo][:skolko]
itog = {'v_zadanii': len(zad), 'ranee': len(gotovo), 'v_vyzove': len(ochered),
        'ssylka_nayd': 0, 'ne_nashli': 0, 'inn_ne_sovpal': 0, 'oshibok': 0}
if not ochered:
    print(json.dumps(itog, ensure_ascii=False))
    sys.exit()

from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    kw = {'headless': True, 'args': ['--no-sandbox']}
    e = hrom()
    if e:
        kw['executable_path'] = e
    br = p.chromium.launch(**kw)
    pg = br.new_context(user_agent=UA, locale='ru-RU', ignore_https_errors=True).new_page()
    for z in ochered:
        r = {'fakt_id': z['fakt_id'], 'inn': z['inn'], 'ts': time.strftime('%Y-%m-%d %H:%M:%S')}
        # фраза поиска: название закупки без ведущего номера и без хвоста «машина»
        fraza = re.sub(r'^\s*\d{4,10}\s*', '', z['tekst'])
        fraza = re.sub(r'\s*(машина|расходник|узел)\s*$', '', fraza).strip(' .«»"')[:160]
        r['fraza'] = fraza
        try:
            pg.goto(POISK + urllib.parse.quote(fraza), timeout=90000,
                    wait_until='domcontentloaded')
            pg.wait_for_timeout(2500)
            adresa = []
            for a in pg.query_selector_all('a[href*="regNumber="]'):
                h = a.get_attribute('href') or ''
                if 'regNumber=' in h:
                    adresa.append(h if h.startswith('http') else 'https://zakupki.gov.ru' + h)
            if not adresa:
                r['verdikt'] = 'поиск ничего не нашёл'
                itog['ne_nashli'] += 1
            else:
                kand = adresa[0]
                pg.goto(kand, timeout=90000, wait_until='domcontentloaded')
                pg.wait_for_timeout(2000)
                t = re.sub(r'\s+', ' ', pg.inner_text('body'))
                sovp = len(slova(fraza) & slova(t)) / max(1, len(slova(fraza)))
                r['kartochka'] = kand
                r['inn_na_stranice'] = z['inn'] in t
                r['dolya_slov'] = round(sovp, 2)
                if z['inn'] in t and sovp >= 0.6:
                    r['verdikt'] = 'ссылка найдена'
                    i = t.find(fraza[:40])
                    r['citata'] = t[max(0, i - 60):i + 220] if i >= 0 else t[:220]
                    itog['ssylka_nayd'] += 1
                else:
                    r['verdikt'] = 'карточка не та (ИНН или текст не сошлись)'
                    itog['inn_ne_sovpal'] += 1
        except Exception as ex:
            r['verdikt'] = 'ошибка'
            r['oshibka'] = str(ex)[:150]
            itog['oshibok'] += 1
        with open(OUT, 'a', encoding='utf-8') as f:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
    br.close()
print(json.dumps(itog, ensure_ascii=False))
