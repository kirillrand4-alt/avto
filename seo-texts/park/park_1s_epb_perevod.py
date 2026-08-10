# -*- coding: utf-8 -*-
"""Проверка перевода ссылок «номер ЭПБ → карточка monitor-pb».

Дефект, который это чинит: 279 фактов парка получили ссылкой ПОИСК ПО ЕИС с номером
заключения ЭПБ в строке запроса (`zakupki.gov.ru/...searchString=59-ТУ-02012-2018`).
Портал закупок такого номера не знает — ссылка открывается, но не доказывает ничего.
Правильный адрес: `monitor-pb.ru/conclusion/<номер>`.

Переводить вслепую нельзя: карточка может принадлежать другому эксплуатанту. Поэтому
здесь каждая новая ссылка ОТКРЫВАЕТСЯ и сверяется ИНН на странице с ИНН факта. Наружу
идёт только то, где ИНН совпал; остальное честно помечается.

Пишем в C:\\sender\\park_epb_perevod.jsonl с fsync — переживает рестарт.
Запуск: panel_py, argv = [<сколько за вызов>]
"""
import json, os, re, sys, time

ZAD = r'C:\sender\_epb_perevod.json'
OUT = r'C:\sender\park_epb_perevod.jsonl'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')


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
                v.add(json.loads(ln)['rowid'])
            except Exception:
                pass
    return v


skolko = int(sys.argv[1]) if len(sys.argv) > 1 else 120
zad = json.load(open(ZAD, encoding='utf-8'))
gotovo = sdelano()
ochered = [z for z in zad if z['rowid'] not in gotovo][:skolko]
itog = {'v_zadanii': len(zad), 'ranee': len(gotovo), 'v_vyzove': len(ochered),
        'inn_sovpal': 0, 'inn_drugoy': 0, 'net_stranicy': 0, 'oshibok': 0}
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
        r = dict(z)
        r['ts'] = time.strftime('%Y-%m-%d %H:%M:%S')
        try:
            otv = pg.goto(z['novaya'], timeout=70000, wait_until='domcontentloaded')
            pg.wait_for_timeout(1500)
            t = re.sub(r'\s+', ' ', pg.inner_text('body'))
            r['http'] = otv.status if otv else None
            r['znakov'] = len(t)
            # «Эксплуатант ... ИНН <10-12 цифр>» — владелец машины, а не экспертная организация
            m = re.search(r'Эксплуатант\s+(.{0,120}?)\s+ИНН\s+(\d{10,12})', t)
            r['ekspluatant'] = m.group(1) if m else ''
            r['inn_na_stranice'] = m.group(2) if m else ''
            i = t.find('Объект экспертизы')
            r['obekt'] = t[i:i + 240] if i >= 0 else ''
            if not m or r['znakov'] < 400:
                r['verdikt'] = 'страница без карточки'
                itog['net_stranicy'] += 1
            elif r['inn_na_stranice'] == z['inn']:
                r['verdikt'] = 'ИНН совпал — ссылку меняем'
                itog['inn_sovpal'] += 1
            else:
                r['verdikt'] = 'ИНН ДРУГОЙ — не меняем'
                itog['inn_drugoy'] += 1
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
