# -*- coding: utf-8 -*-
"""Все заключения ЭПБ предприятия ПО ОДНОМУ ИНН — прямо с его карточки в реестре.

ЗАЧЕМ. Реестр `monitor-pb.ru` — единственный источник, где по ИНН сразу видно, КАКИЕ машины
стоят у предприятия и КОГДА истекает срок экспертизы. Мы качали его полнотекстовым поиском по
словам («компрессор», «воздуходувка»), собирая тысячи строк и потом отфильтровывая своё. При
этом `mpb_harvest.py` САМ строит адрес карточки владельца `monitor-pb.ru/customer/<ИНН>` и
кладёт его в колонку `istochnik_zakazchik` — то есть страница «все заключения этого ИНН»
существует и нам известна, а разбора её не было. Каталог модулей 03.08 назвал это самой дешёвой
доработкой во всём наборе, и вот она.

Чем это лучше поиска по словам:
  * ноль лишнего: только заключения этого предприятия, отбирать не нужно;
  * видно ВСЕ технические устройства, а не только те, где слово совпало с нашим запросом;
  * `Действует до` даёт срок — главный сигнал момента: экспертиза кончается, значит машину
    придётся либо продлевать, либо менять.

Правило владельца соблюдено: ничего не отсеиваем. Наши машины помечаются колонкой
`nashe_oborudovanie`, остальное остаётся в файле со своим типом.

Использование:
    python3 mpb_po_inn.py 2124009521 --tolko-mashiny
    python3 mpb_po_inn.py --spisok inns.txt --out epb-po-inn.csv
"""
import csv
import html
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BAZA = 'https://monitor-pb.ru'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
PAUZA = float(os.environ.get('MPB_PAUZA', '1.0'))

# Разметка РЕЕСТРА и разметка КАРТОЧКИ разные, и это стоило мне прогона с нулём: на карточке
# объект лежит в `title` у <td>, в реестре — в `title` у <button> внутри <td>, а номер завёрнут
# в <span> с кнопкой «скопировать». Поэтому строку разбираю по частям, а не одним жадным
# шаблоном: так поломка разметки в одном столбце не обнуляет всю строку.
TR = re.compile(r'<tr>(.*?)</tr>', re.S)
NOMER = re.compile(r'href="/conclusion/([^"]+)"[^>]*>([^<]+)</a>')
DATA = re.compile(r'tabular-nums[^>]*>([\d.]{8,10})<')
EKSPL = re.compile(r'href="/customer/(\d+)"[^>]*>([^<]*)</a>')
OBEKT = re.compile(r'<button[^>]*title="([^"]{20,})"')
TIP = re.compile(r'<span title="([^"]*)"[^>]*class="[^"]*font-mono[^"]*"[^>]*>([^<]{1,6})</span>')
EO = re.compile(r'href="/org/(\d+)"[^>]*>([^<]*)</a>')


def _stroki(h):
    """Разбор списка заключений построчно. Пустой список означает СБОЙ разбора, а не «нет данных»."""
    out = []
    for tr in TR.findall(h):
        n = NOMER.search(tr)
        if not n:
            continue
        o = OBEKT.search(tr)
        t = TIP.search(tr)
        e = EO.search(tr)
        d = DATA.search(tr)
        x = EKSPL.search(tr)
        out.append({'kod': n.group(1), 'nomer': n.group(2).strip(),
                    'data': d.group(1) if d else '',
                    'zakazchik': html.unescape(x.group(2)) if x else '',
                    'obekt': html.unescape(o.group(1)) if o else '',
                    'tip': t.group(2).strip() if t else '',
                    'tip_polno': html.unescape(t.group(1)) if t else '',
                    'org_id': e.group(1) if e else '', 'org': html.unescape(e.group(2)) if e else '',
                    'do': _bez_tegov(tr[tr.rfind('</a>'):])[:60]})
    return out


# Что считаем СВОИМ. Отдельной колонкой, а не фильтром: предприятие с центробежной машиной
# интересно целиком, включая его прочие устройства — по ним видно масштаб площадки.
NASHE = re.compile(r'компрессор|воздуходувк|нагнетател|турбокомпрессор|турбовоздуходувк|'
                   r'\bЦК-|\bК-(?:250|345|350|500|905|1500|3000)|\bТВ[- ]?\d{2,3}', re.I)
# ЦЕНТРОБЕЖНОСТЬ — только про КОМПРЕССОР или воздуходувку, НИКОГДА про насос.
# Замер на ПАО «Химпром», 5 724 заключения: первая версия искала слово «центробежн» и пометила
# 462 записи, из которых 450 оказались НАСОСАМИ и лишь 8 компрессорами. Реестр полон насосов, и
# слово «центробежный» у них законное: принцип тот же, машина другая, продавцу компрессоров
# бесполезна. Поэтому требуем, чтобы рядом стояла именно наша машина. Насосы не выбрасываю —
# помечаю колонкой `nasos`, правило владельца «разделять, а не отсеивать».
CENTRO = re.compile(
    r'центробежн\w*\s+(?:компрессор|воздуходувк|нагнетател)|'
    r'(?:компрессор|воздуходувк|нагнетател)\w*\s+центробежн|'
    r'турбокомпрессор|турбовоздуходувк|турбогазодувк|нагнетател\w*\s*(?:ГПА|газа)|'
    r'\bЦК-\d|\bК-(?:250|345|350|500|905|1500|3000)(?:\b|[-/])|\b43ВЦ|\bТКА-|'
    r'\bТВ[- ]?\d{2,3}\b|Centac|Elliott|Cooper[- ]Bessemer|Siemens\s+STC', re.I)
# `\bнасос` мимо: в реестре машина зовётся «ЭЛЕКТРОнасос центробежный герметичный» и
# «агрегат ЭЛЕКТРОНАСОСный», где границы слова перед «насос» нет. На тех же 5 724
# заключениях это пропустило 67 насосов в «центробежные». Граница снята, добавлены шнек и
# дымосос — тоже центробежные по принципу и тоже не наша машина.
NASOS = re.compile(r'насос|\bшнек|дымосос', re.I)


def _bez_tegov(s):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', s or ''))).strip()


def _vzyat(url, popytok=3):
    for p in range(popytok):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            return urllib.request.urlopen(req, timeout=60).read().decode('utf-8', 'replace')
        except Exception as e:  # noqa: BLE001
            if p == popytok - 1:
                return f'__ОШИБКА__ {type(e).__name__}: {str(e)[:80]}'
            time.sleep(1.5 * (p + 1))


def po_inn(inn, max_stranic=400, tolko_tu=False):
    """Все заключения одного ИНН. Возвращает (строки, ошибка).

    ВАЖНО ПРО АДРЕС. Карточка `/customer/<ИНН>` показывает только ПОСЛЕДНИЕ 10 заключений и
    пагинации не имеет — я на этом сначала и обожглась, забрав 10 строк и решив, что это всё.
    Полный список живёт по другому адресу: `/conclusions?exploiter=<ИНН>&page=N`, по 25 строк на
    страницу. У ПАО «Химпром» там 279 страниц, то есть около 7 000 заключений против 10 на
    карточке.

    `tolko_tu=True` добавляет `&type=ТУ` — только технические устройства, то есть МАШИНЫ, без
    зданий, трубопроводов и документации. Это то, что нужно продавцу компрессоров.

    Число страниц берётся из самих ссылок пагинации, а не угадывается: страница без НОВЫХ строк
    означает конец. Полагаться на «страница пустая» нельзя — реестр отдаёт ту же первую страницу
    на непонятный ему параметр, и цикл ушёл бы в вечность.
    """
    out, seen = [], set()
    imya = ''
    predel = max_stranic
    st = 1
    while st <= predel:
        url = f'{BAZA}/conclusions?exploiter={inn}'
        if tolko_tu:
            url += '&type=%D0%A2%D0%A3'
        if st > 1:
            url += f'&page={st}'
        h = _vzyat(url)
        if h.startswith('__ОШИБКА__'):
            return out, h
        if st == 1:
            # Шаблон должен пережить ЛЮБОЙ порядок параметров: с `&type=ТУ` ссылка выглядит
            # как `exploiter=<инн>&amp;type=%D0%A2%D0%A3&amp;page=295`, и жёсткое «page сразу
            # после exploiter» давало ноль страниц. Разведка по 1 853 ИНН из-за этого показала
            # «у всех по 1 странице», включая Газпром нефтехим Салават с его 295.
            stranicy = [int(x) for x in
                        re.findall(r'href="/conclusions\?[^"]*exploiter=%s[^"]*page=(\d+)' % inn, h)]
            if stranicy:
                predel = min(max_stranic, max(stranicy))
            m = re.search(r'title="([^"]{0,120})"[^>]*>\s*%s' % inn, h)
        rows = _stroki(h)
        if not rows:
            break
        novyh = 0
        for r in rows:
            if r['nomer'] in seen:
                continue
            seen.add(r['nomer'])
            novyh += 1
            if not imya:
                imya = r['zakazchik']
            ob = r['obekt']
            out.append({
                'inn': inn, 'predpriyatie': imya or r['zakazchik'], 'nomer': r['nomer'],
                'data': r['data'], 'obekt': ob[:600], 'tip': r['tip'],
                'tip_rasshifrovka': r['tip_polno'], 'ekspertnaya_org': r['org'],
                'inn_eo': r['org_id'], 'vyvod': r['do'], 'deystvuet_do': '',
                'nashe_oborudovanie': 'да' if (NASHE.search(ob) and not NASOS.search(ob)) else '',
                'centrobezhnoe': 'да' if (CENTRO.search(ob) and not NASOS.search(ob)) else '',
                'nasos': 'да' if NASOS.search(ob) else '',
                'ssylka': f'{BAZA}/conclusion/{r["kod"]}'})
        if not novyh:
            break
        st += 1
        time.sleep(PAUZA)
    return out, ''


# Срок ЭПБ живёт НЕ в реестре, а на карточке заключения. В списке последний столбец — это
# ВЫВОД экспертизы («соответствует» 5 469, «не в полной мере» 239, «не соответствует» 5 из
# 5 724 у Химпрома), и я сначала записала его в колонку `deystvuet_do`, то есть модуль обещал
# срок, а отдавал вердикт. Колонка переименована в `vyvod`, а настоящая дата берётся отсюда.
# Двух формулировок мало не бывает: живое заключение подписано «Действует до 05.06.2031»,
# просроченное — «Срок истёк 31.12.2022», и первая версия шаблона видела только первую,
# поэтому 36 карточек из 94 отдали «нет в карточке». А просроченные-то и есть цель: машина
# без действующей ЭПБ либо стоит, либо её меняют.
SROK = re.compile(r'(?:Действует\s+до|Срок\s+ист[её]к(?:\s+с)?)\s*(?:<[^>]+>\s*)*(\d{2}\.\d{2}\.\d{4})')
STATUS = re.compile(r'(Действует|Срок\s+ист[её]к|Аннулирован\w*|Приостановлен\w*)')


def dobrat_sroki(rows, potokov=6, tolko_nashe=True):
    """Дозаписать `deystvuet_do` и `status` с карточек заключений.

    Отдельным шагом и по умолчанию только для наших машин: карточек у одного предприятия
    тысячи, а срок нужен там, где он и есть сигнал момента — на компрессорах и воздуходувках.
    Строку, у которой карточку не забрали, помечаю `сбой`, а не оставляю пустой: пусто и
    «не достали» — разные вещи, и по правилу В8 ноль это отказ прибора, пока не доказано иное.
    """
    celi = [r for r in rows
            if not tolko_nashe or r.get('nashe_oborudovanie') or r.get('centrobezhnoe')]

    def odin(r):
        h = _vzyat(r['ssylka'])
        if h.startswith('__ОШИБКА__'):
            r['deystvuet_do'] = 'сбой'
            return
        m = SROK.search(h)
        s = STATUS.search(h)
        r['deystvuet_do'] = m.group(1) if m else 'нет в карточке'
        r['status'] = s.group(1) if s else ''

    with ThreadPoolExecutor(max_workers=potokov) as ex:
        list(ex.map(odin, celi))
    return sum(1 for r in celi if re.match(r'\d{2}\.', r.get('deystvuet_do') or ''))


SLOVA = ['компрессор', 'воздуходувка', 'нагнетатель', 'турбокомпрессор', 'газодувка']


def po_inn_slova(inn, slova=None, max_stranic=20):
    """Только НАШИ машины предприятия: полнотекстовый запрос, суженный по владельцу ОПО.

    ЗАЧЕМ ЭТО ЕСТЬ. Разведка 03.08 по всем 1 853 нашим предприятиям: заключения на
    технические устройства есть у 1 061, суммарно 79 057 страниц — около двух миллионов
    заключений. Качать их целиком ради компрессоров бессмысленно: у АО «Газпромнефть-ННГ»
    2 629 страниц, у Газпром добыча Ямбург 2 117, у Лукойл-Пермь 1 861.

    Оказалось, оба параметра работают вместе: `q=<слово>&exploiter=<ИНН>&type=ТУ`. У той же
    «Газпромнефть-ННГ» это 21 строка на одной странице вместо 2 629 страниц. Проверено
    контролем: с несуществующим ИНН тот же запрос отдаёт НОЛЬ строк, то есть сужение
    действительно применяется, а не игнорируется.

    Плата за дешевизну названа честно: выдача полнотекстовая, поэтому вместе с машинами
    приходят трубопроводы «в здании компрессоров» и подобное. Отсеивать их не надо —
    признаки `nashe_oborudovanie` и `centrobezhnoe` разложат, а трубопровод останется в
    файле со своим типом.
    """
    out, seen = [], set()
    imya = ''
    for slovo in (slova or SLOVA):
        st = 1
        while st <= max_stranic:
            qs = {'q': slovo, 'exploiter': inn, 'type': 'ТУ'}
            if st > 1:
                qs['page'] = st
            h = _vzyat(f'{BAZA}/conclusions?' + urllib.parse.urlencode(qs))
            if h.startswith('__ОШИБКА__'):
                return out, f'{slovo}: {h}'
            rows = _stroki(h)
            if not rows:
                break
            novyh = 0
            for r in rows:
                if r['nomer'] in seen:
                    continue
                seen.add(r['nomer'])
                novyh += 1
                imya = imya or r['zakazchik']
                ob = r['obekt']
                nas = bool(NASOS.search(ob))
                out.append({
                    'inn': inn, 'predpriyatie': imya or r['zakazchik'], 'nomer': r['nomer'],
                    'data': r['data'], 'obekt': ob[:600], 'tip': r['tip'],
                    'tip_rasshifrovka': r['tip_polno'], 'ekspertnaya_org': r['org'],
                    'inn_eo': r['org_id'], 'vyvod': r['do'], 'deystvuet_do': '', 'status': '',
                    'nashli_po': slovo,
                    'nashe_oborudovanie': 'да' if (NASHE.search(ob) and not nas) else '',
                    'centrobezhnoe': 'да' if (CENTRO.search(ob) and not nas) else '',
                    'nasos': 'да' if nas else '',
                    'ssylka': f'{BAZA}/conclusion/{r["kod"]}'})
            if not novyh:
                break
            st += 1
            time.sleep(PAUZA)
    return out, ''


def main():
    kol = ['inn', 'predpriyatie', 'nomer', 'data', 'obekt', 'tip', 'tip_rasshifrovka',
           'ekspertnaya_org', 'inn_eo', 'vyvod', 'deystvuet_do', 'status',
           'nashe_oborudovanie', 'centrobezhnoe', 'nasos', 'ssylka']
    if '--spisok' in sys.argv:
        inns = [x.strip() for x in open(sys.argv[sys.argv.index('--spisok') + 1],
                                        encoding='utf-8') if x.strip()]
    else:
        inns = [a for a in sys.argv[1:] if a.isdigit()]
    if not inns:
        sys.exit(__doc__)
    tu = '--tolko-mashiny' in sys.argv
    out = sys.argv[sys.argv.index('--out') + 1] if '--out' in sys.argv else 'epb-po-inn.csv'
    threads = int(sys.argv[sys.argv.index('--threads') + 1]) if '--threads' in sys.argv else 4
    with ThreadPoolExecutor(max_workers=threads) as p:
        rez = list(p.map(lambda i: (i,) + po_inn(i, tolko_tu=tu), inns))
    vse = []
    for inn, rows, err in rez:
        # Ноль и сбой — разные исходы. Молчаливый ноль уже стоил прошлым сессиям выводов.
        print(f'{inn}: заключений {len(rows)}'
              f'{", из них наших " + str(sum(1 for r in rows if r["nashe_oborudovanie"])) if rows else ""}'
              f'{" | СБОЙ: " + err if err else ""}', file=sys.stderr)
        vse += rows
    if '--bez-srokov' not in sys.argv:
        n = dobrat_sroki(vse)
        print(f'сроки ЭПБ добраны с карточек: {n}', file=sys.stderr)
    with open(out, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=kol, delimiter=';', extrasaction='ignore')
        w.writeheader()
        w.writerows(vse)
    print(f'\nвсего строк: {len(vse)} | предприятий: {len(set(r["inn"] for r in vse))} | '
          f'наших машин: {sum(1 for r in vse if r["nashe_oborudovanie"])} | '
          f'центробежных: {sum(1 for r in vse if r["centrobezhnoe"])} → {out}', file=sys.stderr)


if __name__ == '__main__':
    main()
