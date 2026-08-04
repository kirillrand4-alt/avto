# -*- coding: utf-8 -*-
"""Карточки площадки по НАШИМ предприятиям, а не по словам. Догрузка 292 покупателей.

ПОЧЕМУ ЭТО САМАЯ ДОРОГАЯ РАБОТА СЕЙЧАС. Разбор 9 335 карточек дал 92 технаря с личным
мобильным и 8 предприятий P25, закрытых по букве ТЗ. Но карточки собирались по СЛОВАМ
(«компрессор», «воздуходувка»), и наших покупателей среди них оказалось только 21.
Ещё у 292 компания на площадке опознана, а карточки не выкачаны — включая 65 из
первой сотни по продажам. При наличии карточек предприятие закрывается примерно в
двух случаях из пяти, значит цена этих 292 измеряется десятками закрытий.

И ни одного запроса из общего пула xmlriver: площадка отвечает нам напрямую.

КАК ЭТО ВОЗМОЖНО БЕЗ ПОИСКА ПО СЛОВАМ. У формы списка есть поле `company_id`, которое
в словарном режиме оставалось пустым. Ставим его — и получаем все закупки предприятия,
без слов вовсе. Форма снята с живой страницы, а не угадана.

ЗАСЛОН НА ПАДЕНИЕ СТРАНИЦЫ — С САМОГО НАЧАЛА И ПРОВЕРЕННЫЙ. В сборщике по словам он
был написан, но МЁРТВ: проверялось `h is None`, а `vzyat` при провале возвращает
строку «__ОШИБКА__ ...». Ветка не срабатывала ни разу, отчёт всегда печатал «УПАЛО 0»,
и упавшие страницы исчезали молча — под видом пустых. Здесь проверяется признак,
который источник ДЕЙСТВИТЕЛЬНО подаёт, и есть самопроверка `--proba`.

ДЛИННЫЕ ПРОГОНЫ РЕЖУТСЯ. Задание раннера умирает на 1700 с, поэтому состояние лежит в
потоке jsonl и повторный запуск продолжает с места. Упавшее предприятие очередь НЕ
закрывает: запись со сбоем пройденной не считается — правило, за которое 1-я сессия
заплатила двадцатью целями.
"""
import collections
import csv
import html
import json
import os
import re
import sys
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

POTOK = r'C:\sender\_ops\p25-tp-po-kompaniyam.jsonl'
SVYAZ = r'C:\seostat\drop\drop-storage\tp-zakupki-po-vladelcam.csv'
TP_RAW = 'tp_raw.json'
LIST_URL = 'https://www.tender.pro/api/tenders/list'
CARD_URL = 'https://www.tender.pro/api/tender/%s/view_public'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0 Safari/537.36')

ID_TENDER = re.compile(r'/api/tender/(\d+)/view')
STRANIC = re.compile(r'page=(\d+)')
TEG = re.compile(r'<[^>]+>')


def bez_tegov(s):
    return html.unescape(TEG.sub(' ', s or '')).replace('&nbsp;', ' ').strip()


def vzyat(url, popytok=4):
    """Вернуть текст или строку-признак ошибки. Признак ОДИН и он проверяем."""
    for p in range(popytok):
        try:
            req = urllib.request.Request(
                url, headers={'User-Agent': UA, 'Accept-Language': 'ru,en;q=0.8'})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode('utf-8', 'replace')
        except Exception as e:  # noqa: BLE001
            if p == popytok - 1:
                return '__ОШИБКА__ %s: %s' % (type(e).__name__, str(e)[:80])
            time.sleep(1.5 * (p + 1))


def upalo(h):
    """Единственное место, где решается «страница не загрузилась». Ровно один признак."""
    return (not h) or h.startswith('__ОШИБКА__')


def url_spiska(cid, page=1):
    """Список закупок ОДНОГО предприятия: слово пустое, company_id заполнен."""
    q = {'sid': '', 'good_name': '', 'tender_name': '', 'dateb': '', 'datee': '',
         'tender_type': '100', 'company_name': '', 'tender_state': '100',
         'tender_show_own': '0', 'tender_id': '', 'country': '1', 'region': '0_0',
         'basis': '1', 'tender_promoter': '1', 'tender_officer': '0',
         'company_id': str(cid), 'by': '25', 'order': '3', 'page': str(page)}
    return LIST_URL + '?' + urllib.parse.urlencode(q)


def s_dropa(imya):
    url, tok = os.environ.get('DROP_URL', ''), os.environ.get('DROP_TOKEN', '')
    rq = urllib.request.Request(url.rstrip('/') + '/' + imya)
    rq.add_header('X-Drop-Token', tok)
    return json.loads(urllib.request.urlopen(rq, timeout=300).read().decode('utf-8'))


def uzhe_est_tendery():
    """Номера тендеров, чьи карточки уже выкачаны, — второй раз их не берём."""
    est = set()
    csv.field_size_limit(10 ** 8)
    for p in (r'C:\seostat\drop\drop-storage\tp-kartochki-polnye.csv',):
        if not os.path.exists(p):
            continue
        with open(p, encoding='utf-8-sig', newline='') as f:
            for r in csv.DictReader(f, delimiter=';'):
                if r.get('tender_id'):
                    est.add(str(r['tender_id']).strip())
    return est


def celi():
    """Наши покупатели с опознанной компанией площадки, по месту в продажах."""
    import sqlite3
    d = s_dropa(TP_RAW)
    komp = d.get('компании') or {}
    b = sqlite3.connect('file:C:/seostat/data/p25.db?mode=ro', uri=True)
    nashi = {i: m for i, m in b.execute(
        'select inn, coalesce(mesto_po_summe, 9999) from company')}
    imena = {i: n for i, n in b.execute('select inn, coalesce(predpriyatie,"") from company')}
    out = []
    for inn, mesto in nashi.items():
        z = komp.get(inn) or {}
        if z.get('cid'):
            out.append({'inn': inn, 'cid': str(z['cid']), 'mesto': mesto,
                        'predpriyatie': imena.get(inn, ''),
                        'tp_name': z.get('tp_name', ''), 'tenderov_zayavleno': z.get('тендеров', '')})
    out.sort(key=lambda x: x['mesto'])
    return out


def proba():
    """Самопроверка прибора до прогона: живой ли фильтр и ловится ли падение.

    Без неё прогон на 292 предприятия может честно вернуть нули и выглядеть ответом.
    """
    c = celi()
    print('целей с cid: %d' % len(c))
    if not c:
        return
    z = c[0]
    h = vzyat(url_spiska(z['cid']))
    print('  %s (%s, место %s): упало=%s, ссылок на тендеры %d, страниц %s'
          % (z['tp_name'] or z['predpriyatie'], z['cid'], z['mesto'], upalo(h),
             len(set(ID_TENDER.findall(h or ''))),
             max([int(x) for x in STRANIC.findall(h or '')] or [1])))
    plohoy = vzyat('https://www.tender.pro/api/tenders/list__net_takogo_puti__')
    print('  заведомо битый адрес: упало=%s (должно быть True)' % upalo(plohoy))


def main():
    if '--proba' in sys.argv:
        proba()
        return
    lim = int(sys.argv[sys.argv.index('--lim') + 1]) if '--lim' in sys.argv else 40
    pot = int(sys.argv[sys.argv.index('--potokov') + 1]) if '--potokov' in sys.argv else 4

    gotovo = set()
    if os.path.exists(POTOK):
        for ln in open(POTOK, encoding='utf-8'):
            try:
                z = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            # Упавшая цель очередь НЕ закрывает.
            if not z.get('err'):
                gotovo.add(z['inn'])
    zad = [z for z in celi() if z['inn'] not in gotovo][:lim]
    bylo = uzhe_est_tendery()
    print('к обходу %d, уже пройдено %d, карточек скачано ранее %d'
          % (len(zad), len(gotovo), len(bylo)), file=sys.stderr, flush=True)

    f = open(POTOK, 'a', encoding='utf-8')
    lock = threading.Lock()
    sch = collections.Counter()

    def odna(z):
        h = vzyat(url_spiska(z['cid']))
        if upalo(h):
            return {**z, 'err': (h or '')[:120], 'tendery': [], 'kartochek': 0}
        # ЧИСЛО СТРАНИЦ ИЗ РАЗМЕТКИ НЕ БЕРУ. Проба показала «страниц 39706» у
        # предприятия со 192 закупками: шаблон `page=(\d+)` ловит не только постраничную
        # навигацию. Верить ему — значит тянуть сорок пустых страниц на каждое
        # предприятие. Признак конца надёжнее и берётся из самих данных: страница, не
        # добавившая НИ ОДНОГО нового номера, — последняя.
        tid = list(dict.fromkeys(ID_TENDER.findall(h)))
        upavshih, stranic = 0, 1
        for p in range(2, 41):
            hp = vzyat(url_spiska(z['cid'], p))
            if upalo(hp):
                upavshih += 1
                break
            novyh_na_stranice = [x for x in ID_TENDER.findall(hp) if x not in tid]
            if not novyh_na_stranice:
                break
            tid += novyh_na_stranice
            stranic = p
        novye = [t for t in tid if t not in bylo]
        kart = []
        for t in novye[:200]:
            hc = vzyat(CARD_URL % t)
            if upalo(hc):
                upavshih += 1
                continue
            kart.append({'tender_id': t, 'html_znakov': len(hc),
                         'tekst': bez_tegov(hc)[:60000]})
        return {**z, 'err': '', 'stranic': stranic, 'tenderov': len(tid),
                'novyh': len(novye), 'stranic_upalo': upavshih,
                'kartochki': kart, 'kartochek': len(kart)}

    with ThreadPoolExecutor(max_workers=pot) as ex:
        for r in ex.map(odna, zad):
            with lock:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
                f.flush()
                if r['err']:
                    sch['предприятие не открылось'] += 1
                elif not r['kartochek']:
                    sch['закупок нет или все уже скачаны'] += 1
                else:
                    sch['КАРТОЧКИ ДОБЫТЫ'] += 1
                sch['карточек всего'] += r['kartochek']
                sch['страниц упало'] += r.get('stranic_upalo', 0)
    f.close()
    for k, v in sch.most_common():
        print('REC %s\t%d' % (k, v))
    print('ИТОГ ' + json.dumps({'спрошено предприятий': len(zad)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
