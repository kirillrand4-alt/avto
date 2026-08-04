# -*- coding: utf-8 -*-
"""Карточки площадки по НАШИМ предприятиям, а не по словам. Догрузка 292 покупателей.

ПОЧЕМУ ЭТО САМАЯ ДОРОГАЯ РАБОТА СЕЙЧАС. Разбор 9 335 карточек дал 92 технаря с личным
мобильным и 8 предприятий P25, закрытых по букве ТЗ. Но карточки собирались по СЛОВАМ
(«компрессор», «воздуходувка»), и наших покупателей среди них оказалось только 21.
Ещё у 292 компания на площадке опознана, а карточки не выкачаны — включая 65 из
первой сотни по продажам. При наличии карточек предприятие закрывается примерно в
двух случаях из пяти, значит цена этих 292 измеряется десятками закрытий.

И ни одного запроса из общего пула xmlriver: площадка отвечает нам напрямую.

КАК ЭТО ВОЗМОЖНО БЕЗ ПОИСКА ПО СЛОВАМ. Форма списка сужается ИМЕНЕМ предприятия
текстом. Поле `company_id` в ней есть, но оно не фильтрует ничего — установлено
замером с контролем, а не прочтением формы: первый заход поставил `company_id` и
получил «тендеров 2820» одинаково у всех восьми предприятий подряд, то есть общую
выдачу площадки под видом выдачи по компании.

Фильтр по имени ШИРОКИЙ: «Апатит» ловит несколько разных компаний. Поэтому имя лишь
сужает выдачу на стороне площадки, а принадлежность решается на нашей — сверкой
`company_id` в КАЖДОЙ строке списка. Широкий отбор плюс точная сверка надёжнее, чем
доверие одному параметру.

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
# Строка выдачи целиком: номер тендера И id компании, которой он принадлежит. Нужна
# именно она, а не просто номера: фильтр площадки по имени ШИРОКИЙ, и «Апатит» ловит
# несколько компаний. Точность добирается сверкой company_id уже по нашей стороне.
ROW = re.compile(
    r'<td[^>]*class="pr-0 tender__name"[^>]*>.*?href="/api/tender/(\d+)/view_public"[^>]*>'
    r'(.*?)</a>.*?</td>\s*<td[^>]*>([\d.]{0,10})</td>\s*<td[^>]*>([^<]{0,30})</td>'
    r'.*?href="/api/company/(\d+)/view[^"]*"[^>]*>([^<]{0,200})</a>', re.S)
GOROD_V_IMENI = re.compile(r'\s*\([^)]*\)\s*$')
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


def url_spiska(imya, page=1):
    """Список закупок предприятия. Фильтр — ИМЯ ТЕКСТОМ, и это установлено замером.

    Первый заход ставил `company_id`, и прогон вернул «тендеров 2820» ОДИНАКОВО у всех
    восьми предприятий подряд — то есть общую выдачу площадки, выданную за выдачу по
    компании. Проба перед тем прогоном спрашивала «жив ли фильтр» так: пришли ли ссылки
    на тендеры. Пришли — значит жив. Это не проверка: непустая выдача бывает и без
    фильтра.

    Отдельный замер (`p25_tp_filtr_proba.py`) прогнал семь имён параметра с контролем
    «два разных значения должны дать разное, заведомо битое — пустое»:

        company_id, sid, promoter_id, organizator_id, customer_id -> 25/25/25, не сужают
        company_name текстом -> 25 / 25 / бессмыслица 0, различает

    Ни один id не фильтрует вовсе; фильтрует только имя текстом. Город в скобках из
    имени убираю: он часть нашей пометки, а не названия на площадке.
    """
    q = {'sid': '', 'good_name': '', 'tender_name': '', 'dateb': '', 'datee': '',
         'tender_type': '100', 'company_name': GOROD_V_IMENI.sub('', imya),
         'tender_state': '100',
         'tender_show_own': '0', 'tender_id': '', 'country': '1', 'region': '0_0',
         'basis': '1', 'tender_promoter': '1', 'tender_officer': '0',
         'company_id': '', 'by': '25', 'order': '3', 'page': str(page)}
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
    # ПРОБА ОБЯЗАНА ПОКАЗАТЬ РАЗЛИЧЕНИЕ. Прежняя спрашивала «пришли ли ссылки» и на
    # неработающем фильтре отвечала «жив», после чего прогон собрал 1 599 карточек
    # общей выдачи и приписал их восьми предприятиям. Непустая выдача — не признак
    # фильтра. Признак фильтра: два разных входа дают разное, бессмыслица даёт ноль.
    nabory = []
    for z in c[:2]:
        imya = z['tp_name'] or z['predpriyatie']
        h = vzyat(url_spiska(imya))
        svoi = [t for t, _p, _s, _d, cid, _cm in ROW.findall(h or '')
                if str(cid) == str(z['cid'])]
        nabory.append(set(ID_TENDER.findall(h or '')))
        print('  %-34s всего в выдаче %2d, из них СВОИХ по cid %2d'
              % (imya[:34], len(nabory[-1]), len(svoi)))
    bred = vzyat(url_spiska('кастрюлякастрюля'))
    n_bred = len(set(ID_TENDER.findall(bred or '')))
    razlichaet = len(nabory) == 2 and nabory[0] != nabory[1]
    print('  бессмыслица в имени: %d строк (должно быть 0)' % n_bred)
    print('  два предприятия дают РАЗНОЕ: %s (должно быть True)' % razlichaet)
    plohoy = vzyat('https://www.tender.pro/api/tenders/list__net_takogo_puti__')
    print('  заведомо битый адрес: упало=%s (должно быть True)' % upalo(plohoy))
    print('ИТОГ ' + json.dumps({'фильтр различает': razlichaet,
                                'бессмыслица даёт ноль': n_bred == 0,
                                'падение ловится': upalo(plohoy)}, ensure_ascii=False))


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
        imya_dlya_poiska = z['tp_name'] or z['predpriyatie']
        if not imya_dlya_poiska:
            return {**z, 'err': 'имени предприятия на площадке нет — искать нечем',
                    'kartochki': [], 'kartochek': 0}
        h = vzyat(url_spiska(imya_dlya_poiska))
        if upalo(h):
            return {**z, 'err': (h or '')[:120], 'tendery': [], 'kartochek': 0}
        # ЧИСЛО СТРАНИЦ ИЗ РАЗМЕТКИ НЕ БЕРУ. Проба показала «страниц 39706» у
        # предприятия со 192 закупками: шаблон `page=(\d+)` ловит не только постраничную
        # навигацию. Верить ему — значит тянуть сорок пустых страниц на каждое
        # предприятие. Признак конца надёжнее и берётся из самих данных: страница, не
        # добавившая НИ ОДНОГО нового номера, — последняя.
        def moi_nomera(html_stranicy):
            """Номера тендеров, у которых id компании РАВЕН нашему. Чужие не берём."""
            svoi, chuzhih = [], 0
            for tnum, _pr, _sz, _do, cid_stroki, _comp in ROW.findall(html_stranicy):
                if str(cid_stroki) == str(z['cid']):
                    svoi.append(tnum)
                else:
                    chuzhih += 1
            return svoi, chuzhih

        tid, chuzhih_vsego = moi_nomera(h)
        vseh_na_stranice = len(set(ID_TENDER.findall(h)))
        upavshih, stranic = 0, 1
        for p in range(2, 41):
            hp = vzyat(url_spiska(imya_dlya_poiska, p))
            if upalo(hp):
                upavshih += 1
                break
            svoi_p, chuzhih_p = moi_nomera(hp)
            chuzhih_vsego += chuzhih_p
            novyh_na_stranice = [x for x in svoi_p if x not in tid]
            # Страница без НАШИХ строк ещё не конец: имя широкое, и наши могут идти
            # дальше. Концом считаю страницу, где нет вообще ничьих строк.
            if not svoi_p and not chuzhih_p:
                break
            if novyh_na_stranice:
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
                'chuzhih_otseyano': chuzhih_vsego, 'na_pervoy_stranice': vseh_na_stranice,
                'imya_poiska': imya_dlya_poiska,
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
