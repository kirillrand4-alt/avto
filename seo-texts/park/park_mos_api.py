# -*- coding: utf-8 -*-
"""Портал поставщиков Москвы: меняем ссылку на открываемую форму и забираем контакт.

Находка 3-й сессии, проверенная у себя: страница `zakupki.mos.ru/need/N` отдаёт 200, но
в теле только шапка портала («ДОБРО ПОЖАЛОВАТЬ НА ПОРТАЛ ПОСТАВЩИКОВ»), карточку рисует
скрипт. Рабочие формы:

    /newapi/api/Need/Get?needId=N          -> JSON карточки потребности
    /newapi/api/Auction/Get?auctionId=N    -> JSON карточки котировочной сессии

**Мой первый замер сказал «слово в теле есть» и был неверен**: я искал общее слово
«компрессор», а оно попадалось в новостях и меню портала. Увидел, только когда напечатал
тело целиком — в шапке 1 821 знак и ни одной строки о закупке.

В JSON, кроме предмета и заказчика, лежит `contactPerson` / `contactPhone` /
`contactEmail` — то есть это ещё и контакт с провенансом.

Долговечно: пишем в C:\\sender\\park_mos_api.jsonl с fsync, резюм по id.
Запуск: panel_py, argv = [<сколько ссылок за вызов>]
"""
import json, os, re, sys, time

BAZA = r'C:\sender'
ZAD = os.path.join(BAZA, 'park_mos_zadanie.json')
OUT = os.path.join(BAZA, 'park_mos_api.jsonl')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')


def _hrom():
    k = r'C:\sender\pw-browsers'
    if os.path.isdir(k):
        for d in sorted(os.listdir(k), reverse=True):
            e = os.path.join(k, d, 'chrome-win64', 'chrome.exe')
            if os.path.exists(e):
                return e
    return None


def _sdelano():
    v = set()
    if os.path.exists(OUT):
        with open(OUT, encoding='utf-8', errors='replace') as f:
            for ln in f:
                try:
                    v.add(json.loads(ln)['staraya'])
                except Exception:
                    pass
    return v


def _api(u):
    m = re.search(r'/(need|auction|tender)/(\d+)', u)
    if not m:
        return None
    vid, nid = m.group(1), m.group(2)
    if vid == 'need':
        return 'https://zakupki.mos.ru/newapi/api/Need/Get?needId=' + nid
    if vid == 'auction':
        return 'https://zakupki.mos.ru/newapi/api/Auction/Get?auctionId=' + nid
    return None


def main():
    skolko = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    zad = json.load(open(ZAD, encoding='utf-8'))
    gotovo = _sdelano()
    ochered = [z for z in zad if z['url'] not in gotovo][:skolko]
    itog = {'v_zadanii': len(zad), 'sdelano_ranee': len(gotovo), 'v_vyzove': len(ochered),
            'otdali_kartochku': 0, 's_kontaktom': 0, 'pusto': 0, 'oshibki': []}
    if not ochered:
        print(json.dumps(itog, ensure_ascii=False))
        return
    from playwright.sync_api import sync_playwright
    exe = _hrom()
    with sync_playwright() as p:
        kw = {'headless': True, 'args': ['--no-sandbox']}
        if exe:
            kw['executable_path'] = exe
        br = p.chromium.launch(**kw)
        pg = br.new_context(user_agent=UA, locale='ru-RU',
                            ignore_https_errors=True).new_page()
        for z in ochered:
            api = _api(z['url'])
            r = {'staraya': z['url'], 'novaya': api, 'fakt_id': z.get('fakt_id'),
                 'ts': time.strftime('%Y-%m-%d %H:%M:%S')}
            if not api:
                r['pochemu'] = 'форма не распознана (не need и не auction)'
                itog['pusto'] += 1
            else:
                try:
                    otv = pg.goto(api, timeout=60000, wait_until='domcontentloaded')
                    pg.wait_for_timeout(1200)
                    t = pg.inner_text('body')
                    r['http'] = otv.status if otv else None
                    try:
                        d = json.loads(t)
                    except Exception:
                        d = None
                    if isinstance(d, dict):
                        zak = (d.get('customer') or {})
                        r['zakazchik'] = zak.get('name') or ''
                        r['zakazchik_id'] = zak.get('id')
                        r['predmet'] = (d.get('name') or d.get('subject') or
                                        (d.get('items') or [{}])[0].get('name', '')
                                        if isinstance(d.get('items'), list) else '') or ''
                        r['kontakt_fio'] = d.get('contactPerson') or ''
                        r['kontakt_tel'] = d.get('contactPhone') or ''
                        r['kontakt_email'] = d.get('contactEmail') or ''
                        r['inn'] = (zak.get('inn') or d.get('customerInn') or '')
                        r['znakov'] = len(t)
                        # весь JSON тоже сохраняем: там могут быть позиции с моделями
                        r['telo'] = t[:4000]
                        itog['otdali_kartochku'] += 1
                        if r['kontakt_fio'] or r['kontakt_tel'] or r['kontakt_email']:
                            itog['s_kontaktom'] += 1
                    else:
                        r['pochemu'] = 'ответ не JSON'
                        r['telo'] = t[:300]
                        itog['pusto'] += 1
                except Exception as e:
                    r['oshibka'] = str(e)[:130]
                    itog['oshibki'].append(str(e)[:80])
            with open(OUT, 'a', encoding='utf-8') as f:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
                f.flush()
                os.fsync(f.fileno())
        br.close()
    itog['oshibki'] = itog['oshibki'][:5]
    print(json.dumps(itog, ensure_ascii=False))


if __name__ == '__main__':
    main()
