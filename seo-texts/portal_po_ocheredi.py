# -*- coding: utf-8 -*-
"""Закупки Портала поставщиков Москвы по КАЖДОМУ предприятию очереди.

Отдельный модуль вместо ветки в `ploshchadki_po_ocheredi.py`: тот ходит через `eval_js`, а
03.08 около 19:45 раннер перестал выполнять `eval_js` вовсе — ключей `eval_js_*` в ответе
нет при `http_status: 200` и живой странице. Здесь скрипты не нужны: браузер ВЕДЁТСЯ прямо
на адрес API, тело ответа — чистый JSON, разбор на нашей стороне. Заодно исчезает CORS,
из-за которого приходилось заходить со страницы того же домена.

РЕЦЕПТ, снятый перебором (работает ровно одно сочетание из пяти):
    old.zakupki.mos.ru/api/Cssp/Purchase/Query?queryDto=<JSON>   GET   → 200, count, items
    zakupki.mos.ru/api/…                                          GET   → 200, но HTML оболочки
    old.zakupki.mos.ru/api/…                                      POST  → 405
    /newapi/api/Purchase/Query                                    GET   → 404
Хост обязателен `old.`, метод только GET. Запись соседней сессии «Query отвечает на POST
с JSON-телом» неверна — POST площадка не принимает вовсе.

ОБЯЗАТЕЛЬНО `"proxy": ""`. По умолчанию раннер идёт через мёртвый PROXY_URLV3, и домен
выглядит закрытым (`ERR_TUNNEL_CONNECTION_FAILED`). Из-за этого площадка сутки считалась
доступной только через профиль Дельфина — неправда. И НЕЛЬЗЯ слать `proxy: ''` вместе
с `dolphin_profile`: раннер отвечает `probe-failed: HTTP Error 500`.

ФИЛЬТР: `customerInnOrName` с `contains: true` — подстрочное совпадение по ИНН ИЛИ названию.
Значит теоретически может зацепить чужой 12-значный ИНН, содержащий наш как подстроку,
поэтому принадлежность проверяется по-настоящему: у каждой записи есть `customers[].inn`,
и строки, где нашего ИНН нет, считаются отдельно и помечаются в журнале.

Контроль сужения на каждом прогоне, оба конца:
    9999999999 (бессмыслица)  → count 0
    7701984274 (Мосводоканал) → count 9 438
Один только первый конец не ловит «площадка молча отдаёт пусто всем» — а это у нас уже было.

Использование:
    python3 portal_po_ocheredi.py --kontrol
    python3 portal_po_ocheredi.py --predel 20 --parallel 8
"""
import csv
import json
import os
import subprocess
import sys
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

csv.field_size_limit(10 ** 7)
BAZA = os.path.dirname(os.path.abspath(__file__))
L = os.path.join(BAZA, 'engineers-lens')
C = os.path.join(L, 'centro')
KLIENT = os.path.join(BAZA, 'server', 'run_on_server.py')
OCHERED = os.path.join(L, 'OCHERED-centrobezhnye.csv')
# ОТДЕЛЬНЫЙ ФАЙЛ, не `portal-po-kompaniyam.csv`. Там 26 705 строк прошлого обхода с ДРУГИМ
# набором колонок (8 против наших 12, есть `ploshchadka`). Дозапись своим порядком колонок
# в чужую шапку — та самая порча, что дважды за неделю увела комментарии в колонку почты и
# обнулила 367 платных разборов. Файлы сводятся `svod_tri_sostoyaniya.py`, а не дозаписью.
VYHOD = os.path.join(C, 'portal-po-kompaniyam-inn.csv')
KARTA = os.path.join(C, 'portal-obhod-zhurnal.csv')
COLS = ['inn', 'predpriyatie', 'nomer', 'predmet', 'zakazchik', 'vid', 'summa', 'data',
        'data_konca', 'stadiya', 'region', 'vid_kartochki', 'need_id', 'tender_id',
        'auction_id', 'ssylka', 'ssylka_vneshnyaya']
TAKE = 100               # проверено: площадка отдаёт до 100 записей за раз
STRANIC_MAX = 30         # 3 000 закупок на предприятие
PAUZA = 0.3


def chitat(put):
    return list(csv.DictReader(open(put, encoding='utf-8-sig'), delimiter=';')) \
        if os.path.exists(put) else []


def dovod(imya, po_umolchaniyu):
    return type(po_umolchaniyu)(sys.argv[sys.argv.index(imya) + 1]) \
        if imya in sys.argv else po_umolchaniyu


def probe(url, tayminaut=400):
    zad = {'url': url, 'screenshot': False, 'proxy': '', 'return_html': True,
           'html_cap': 1500000, 'wait_ms': 3000}
    try:
        p = subprocess.run([sys.executable, KLIENT, 'browser_probe',
                            json.dumps(zad, ensure_ascii=False)],
                           capture_output=True, text=True, timeout=tayminaut)
    except subprocess.TimeoutExpired:
        return None, f'раннер не ответил за {tayminaut} с'
    try:
        d = json.loads(p.stdout[p.stdout.index('{'):]).get('data') or {}
    except (ValueError, json.JSONDecodeError):
        return None, (p.stdout or p.stderr or 'пустой ответ раннера')[-200:]
    h = d.get('html') or ''
    if not h:
        return None, (f"тело пусто. ключи: {','.join(sorted(d.keys()))} | "
                      f"http_status={d.get('http_status')} | error={str(d.get('error'))[:120]}")
    if d.get('html_truncated'):
        return None, f'ответ обрезан на {d.get("html_full_len")} знаках — снизить take'
    i, j = h.find('<pre>'), h.rfind('</pre>')
    kus = h[i + 5:j] if (i >= 0 and j > i) else h
    kus = (kus.replace('&quot;', '"').replace('&amp;', '&')
              .replace('&lt;', '<').replace('&gt;', '>'))
    try:
        return json.loads(kus), ''
    except json.JSONDecodeError as e:
        return None, f'ответ не JSON: {str(e)[:70]} | начало: {kus[:120]}'


def zapros(inn, skip, take=TAKE):
    dto = {'filter': {'customerInnOrName': {'value': str(inn), 'contains': True}},
           'withCount': True, 'take': take, 'skip': skip}
    return probe('https://old.zakupki.mos.ru/api/Cssp/Purchase/Query?queryDto='
                 + urllib.parse.quote(json.dumps(dto, ensure_ascii=False)))


def szhat(x, inn):
    zak = x.get('customers') or []
    # Принадлежность проверяем по настоящему полю, а не по факту, что фильтр «применился».
    svoy = any(str((z or {}).get('inn') or '') == str(inn) for z in zak)
    # Маршрут карточки зависит от ТИПА записи, а не от одного «кода». Проверено:
    # `/purchase/<id>` отдаёт «Ничего не нашлось на Портале поставщиков» и 404, а
    # настоящий адрес потребности — `/need/<id>`. Из-за одного общего кода 88 252 уже
    # собранные ссылки ведут в никуда, поэтому теперь пишутся все три идентификатора:
    # ссылку можно пересобрать, не переобходя площадку.
    need, tend, auk = x.get('needId'), x.get('tenderId'), x.get('auctionId')
    if need:
        vid_k, kod, put = 'потребность', need, '/need/'
    elif auk:
        vid_k, kod, put = 'аукцион', auk, '/auction/'
    elif tend:
        vid_k, kod, put = 'тендер', tend, '/tender/'
    else:
        vid_k, kod, put = 'неизвестен', x.get('id') or '', '/purchase/'
    return {'nomer': str(x.get('number') or x.get('externalNumber') or ''),
            'predmet': str(x.get('name') or '')[:300],
            'zakazchik': '; '.join(str((z or {}).get('name') or '') for z in zak)[:200],
            'vid': str(x.get('tenderTypeName') or x.get('federalLawName') or ''),
            'summa': str(x.get('startPrice') or x.get('auctionCurrentPrice') or ''),
            'data': str(x.get('beginDate') or '')[:10],
            'data_konca': str(x.get('endDate') or '')[:10],
            'stadiya': str(x.get('stateName') or ''),
            'region': str(x.get('regionName') or ''),
            'vid_kartochki': vid_k, 'need_id': need or '', 'tender_id': tend or '',
            'auction_id': auk or '',
            'ssylka': 'https://zakupki.mos.ru' + put + str(kod),
            'ssylka_vneshnyaya': str(x.get('externalUrl') or ''),
            'svoy': svoy}


def odno_predpriyatie(inn, stranic):
    rows, vsego, oborvano = [], 0, ''
    for n in range(stranic):
        o, err = zapros(inn, n * TAKE)
        if o is None:
            if n == 0:
                return None, err
            oborvano = err
            break
        vsego = o.get('count') or vsego
        items = o.get('items') or []
        rows.extend(szhat(x, inn) for x in items)
        if len(items) < TAKE:
            break
        time.sleep(PAUZA)
    return {'vsego': vsego, 'rows': rows, 'oborvano': oborvano,
            'vzyato_stranic': (len(rows) + TAKE - 1) // TAKE}, ''


def main():
    predel = dovod('--predel', 10 ** 9)
    parallel = dovod('--parallel', 8)
    # Предел раннера: сверх 30 воркеров задачи не работают, а ждут.
    import predel_rannera
    predel_rannera.preduprezhdenie(parallel)
    stranic = dovod('--stranic', STRANIC_MAX)

    och = chitat(OCHERED)
    if len(och) < 300:
        sys.exit(f'ОСТАНОВКА: очередь {len(och)} строк — пересоберите базу перед обходом.')
    proydeno = {r['inn'] for r in chitat(KARTA)}
    celi = [{'inn': r['inn'], 'predpriyatie': r.get('predpriyatie') or ''}
            for r in och if r['inn'] not in proydeno][:predel]

    bred, err = zapros('9999999999', 0, 5)
    if bred is None:
        sys.exit(f'ОСТАНОВКА: контрольный запрос не прошёл — {err}')
    if (bred.get('count') or 0) > 0:
        sys.exit(f'КОНТРОЛЬ ПРОВАЛЕН: бессмыслица вернула count={bred.get("count")}')
    zhivoy, err = zapros('7701984274', 0, 5)
    if zhivoy is None or (zhivoy.get('count') or 0) == 0:
        sys.exit('КОНТРОЛЬ ПРОВАЛЕН: заведомо непустое предприятие (Мосводоканал) дало ноль '
                 f'— площадка отдаёт пусто всем. {err}')
    print(f'[Портал Москвы] контроль: бессмыслица {bred.get("count")}, '
          f'Мосводоканал {zhivoy.get("count")} | к обходу {len(celi)} '
          f'(пройдено {len(proydeno)})', file=sys.stderr)
    if '--kontrol' in sys.argv or not celi:
        return

    novyy_v = not os.path.exists(VYHOD) or os.path.getsize(VYHOD) == 0
    novyy_k = not os.path.exists(KARTA) or os.path.getsize(KARTA) == 0
    fv = open(VYHOD, 'a', encoding='utf-8-sig', newline='')
    wv = csv.DictWriter(fv, fieldnames=COLS, delimiter=';', extrasaction='ignore')
    if novyy_v:
        wv.writeheader()
    fk = open(KARTA, 'a', encoding='utf-8-sig', newline='')
    wk = csv.DictWriter(fk, fieldnames=['inn', 'predpriyatie', 'vsego', 'vzyato', 'chuzhih',
                                        'pochemu'], delimiter=';', extrasaction='ignore')
    if novyy_k:
        wk.writeheader()

    sch = {'предприятий': 0, 'закупок': 0, 'пусто': 0, 'обрезано потолком': 0,
           'чужих строк': 0, 'сбоев': 0}
    lock = threading.Lock()

    def odno(c):
        return c, odno_predpriyatie(c['inn'], stranic)

    with ThreadPoolExecutor(max_workers=parallel) as pool:
        for nomer, (c, (sv, err)) in enumerate(pool.map(odno, celi), 1):
            with lock:
                if sv is None:
                    sch['сбоев'] += 1
                    print(f'  СБОЙ {c["inn"]}: {err[:150]}', file=sys.stderr, flush=True)
                    continue
                sch['предприятий'] += 1
                rows = sv['rows']
                sch['закупок'] += len(rows)
                if not rows:
                    sch['пусто'] += 1
                chuzhih = sum(1 for x in rows if not x['svoy'])
                sch['чужих строк'] += chuzhih
                obrezano = sv['vsego'] > len(rows) and not sv['oborvano']
                if obrezano:
                    sch['обрезано потолком'] += 1
                pochemu = 'обойдено'
                if sv['oborvano']:
                    pochemu = 'ОБОРВАЛОСЬ: ' + str(sv['oborvano'])[:120]
                elif obrezano:
                    pochemu = (f'ВЗЯТО НЕ ВСЁ: всего {sv["vsego"]}, взято {len(rows)} — '
                               'поднять --stranic')
                elif chuzhih:
                    pochemu = f'{chuzhih} строк без нашего ИНН среди заказчиков — проверить'
                wk.writerow({'inn': c['inn'], 'predpriyatie': c['predpriyatie'],
                             'vsego': sv['vsego'], 'vzyato': len(rows), 'chuzhih': chuzhih,
                             'pochemu': pochemu})
                for x in rows:
                    wv.writerow(dict(x, inn=c['inn'], predpriyatie=c['predpriyatie']))
                fv.flush()
                fk.flush()
                if nomer % 20 == 0 or sv['vsego']:
                    print(f'  [portal] {nomer}/{len(celi)}: {sch}', file=sys.stderr, flush=True)

    fv.close()
    fk.close()
    print(f'готово: {sch}\n→ {VYHOD}\n→ {KARTA}', file=sys.stderr)


if __name__ == '__main__':
    main()
