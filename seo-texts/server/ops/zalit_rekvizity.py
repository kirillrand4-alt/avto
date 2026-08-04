# -*- coding: utf-8 -*-
"""Заполнить реквизиты карточек панели и ВСЕ ОКВЭДы с подписями.

ЗАЧЕМ. Владелец прислал карточку Ставрополькрайводоканала: регион, адрес,
директор, статус ЕГРЮЛ, сайт, почта, выручка, сотрудники, ОКВЭД — всё «—».
Колонки в панели ЕСТЬ (`region`, `adres`, `direktor`, `status_egrul`, `sayt`,
`pochta`, `vyruchka_rub`, `chistaya_pribyl`, `ssch`, `okved`), они просто
пустые: сборка снимка их не наполняла.

ОТКУДА БЕРЁМ, и почему именно так. Замер по нашим 1573 ИНН:
    enrich.db companies    — 1572 (okved, region, site, best_email, director…)
    enrich.db requisites    —  121 (адрес, статус, ОКВЭД полный, сотрудники)
    obzvon-index.db obzvon  —  137
    seo.db call_company     —  131
    enrich.db base_ref      —   67
То есть база обзвона по НАШЕЙ базе почти пуста (она про другие 161k юрлиц), а
главный источник — `companies`. Поэтому источники сливаются по приоритету
качества: requisites (ЕГРЮЛ-выгрузка) > call_company/obzvon (реквизиты базы
обзвона) > companies (наш обогатитель) > base_ref. Первый непустой выигрывает,
и в `istochnik_rekvizitov` пишем, кто дал.

ПОДПИСИ ОКВЭД. Код без названия продавцу бесполезен. Словарь код→название
собираем из `call_company.okved_main/okved_all` (161k строк, там коды УЖЕ с
названиями) плюс из requisites — это бесплатно и локально. Наши коды (голые,
вида «36.00.2») подписываем этим словарём. Владелец просил ВСЕ ОКВЭДы, а не
только основной, поэтому добавляем колонку `okvedy_vse`.

Никаких выдумок: код, которого нет в словаре, остаётся без подписи, а не
получает похожую. Пустое поле честнее правдоподобной ошибки.

По умолчанию СУХОЙ ПРОГОН. Запуск: python zalit_rekvizity.py [--apply]
"""
import json
import os
import re
import shutil
import sqlite3
import sys
import time
from collections import Counter

ЦБ = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
ENRICH = os.getenv('CENTRO_ENRICH_DB', r'C:\sender\enrich.db')
OBZVON = os.getenv('CENTRO_OBZVON_DB', r'C:\sender\obzvon-index.db')
SEO = os.getenv('CENTRO_SEO_DB', r'C:\seostat\data\seo.db')
ПРИМЕНИТЬ = '--apply' in sys.argv
# «01.11 Выращивание зерновых» — код и название рядом
_ПАРА = re.compile(r'(\d{2}(?:\.\d{1,2}){0,3})\s+([А-ЯЁA-Z][^|;,\n]{4,120})')
_КОД = re.compile(r'\d{2}(?:\.\d{1,2}){0,3}')


def ро(путь):
    try:
        if not os.path.exists(путь):
            return None
        cx = sqlite3.connect(f'file:{путь}?mode=ro', uri=True, timeout=30)
        cx.row_factory = sqlite3.Row
        return cx
    except Exception:  # noqa: BLE001
        return None


def строки(cx, табл):
    if cx is None:
        return {}
    try:
        return {str(r['inn']): dict(r) for r in cx.execute(f'SELECT * FROM {табл}')
                if r['inn']}
    except Exception:  # noqa: BLE001
        return {}


def словарь_окведов(*наборы):
    """код -> название. Не перезаписываем: длинное название вытесняет обрезок."""
    d = {}
    for набор in наборы:
        for з in набор.values():
            for поле in ('okved_main', 'okved_all', 'okved', 'okved_all_codes'):
                т = str(з.get(поле) or '')
                if not т:
                    continue
                for код, назв in _ПАРА.findall(т):
                    назв = назв.strip(' .;,')
                    if назв and len(назв) > len(d.get(код, '')):
                        d[код] = назв
    return d


def подписать(текст, словарь):
    """«36.00.2|41.20» -> «36.00.2 Забор и очистка воды | 41.20 Строительство»."""
    коды, видел = [], set()
    for код in _КОД.findall(str(текст or '')):
        if код in видел:
            continue
        видел.add(код)
        назв = словарь.get(код, '')
        коды.append(f'{код} {назв}'.strip())
    return ' | '.join(коды)


def первое(*значения):
    for з in значения:
        с = str(з if з is not None else '').strip()
        if с and с not in ('0', '—', 'None', 'null'):
            return с
    return ''


def _первая_почта(строка):
    """Из «a@x.ru | b@y.ru» — первую: поле pochta в карточке одно."""
    ч = [x.strip() for x in str(строка or '').split('|') if x.strip()]
    return ч[0] if ч else ''


def main():
    цб_ро = ро(ЦБ)
    наши = [str(r['inn']) for r in цб_ро.execute('SELECT inn FROM company')]
    кол = {c[1] for c in цб_ро.execute('PRAGMA table_info(company)')}
    цб_ро.close()

    e, o, s = ро(ENRICH), ро(OBZVON), ро(SEO)
    companies = строки(e, 'companies')
    requisites = строки(e, 'requisites')
    base_ref = строки(e, 'base_ref')
    obzvon = строки(o, 'obzvon')
    call = строки(s, 'call_company')
    for cx in (e, o, s):
        if cx:
            cx.close()
    словарь = словарь_окведов(call, requisites, obzvon, companies)
    print(f'наших ИНН: {len(наши)}; словарь ОКВЭД: {len(словарь)} кодов с названиями')
    print(f'источники: companies {len(companies)}, requisites {len(requisites)}, '
          f'call_company {len(call)}, obzvon {len(obzvon)}, base_ref {len(base_ref)}')

    правки = []
    охват = Counter()
    источники = Counter()
    for инн in наши:
        c = companies.get(инн, {})
        r = requisites.get(инн, {})
        k = call.get(инн, {})
        b = obzvon.get(инн, {})
        f = base_ref.get(инн, {})
        # приоритет: ЕГРЮЛ-реквизиты > база обзвона > наш обогатитель
        знач = {
            'region': первое(r.get('region'), b.get('region'), k.get('region'),
                             c.get('region')),
            'adres': первое(r.get('address'), b.get('address'), k.get('address'),
                            f.get('addr')),
            'direktor': первое(
                ' '.join(x for x in (str(r.get('director') or ''),
                                     str(r.get('director_post') or '')) if x).strip(),
                b.get('director'), k.get('director'), c.get('director')),
            'status_egrul': первое(r.get('status'), b.get('status'), k.get('status')),
            'sayt': первое(c.get('site'), r.get('site_checko'), r.get('site'), b.get('sites'),
                           k.get('sites'), f.get('site'), c.get('cand_site')),
            'pochta': первое(c.get('best_email'), _первая_почта(r.get('emails_checko')), b.get('emails_base'),
                             k.get('emails'), b.get('emails_site')),
            # ЧЕКО ВПЕРЕДИ прочих: это единственный источник, где деньги
            # приходят С ГОДОМ отчётности. Выручка без года вводит в
            # заблуждение сильнее, чем пустое поле: у части предприятий
            # свежайшая отчётность за 2018-й, а выглядит она как сегодняшняя.
            'vyruchka_rub': первое(r.get('revenue_rub'), c.get('revenue_rub'),
                                   b.get('revenue_rub'), b.get('revenue'),
                                   k.get('revenue_num'), k.get('revenue'),
                                   f.get('revenue')),
            'chistaya_pribyl': первое(r.get('profit_rub'), b.get('profit'),
                                      k.get('profit')),
            'ssch': первое(r.get('ssch'), r.get('employees'), b.get('ssch'),
                           k.get('staff')),
            'fin_god': первое(r.get('fin_god')),
            'ssch_god': первое(r.get('ssch_god')),
            'telefony_checko': первое(r.get('phones_checko')),
            'pochty_checko': первое(r.get('emails_checko')),
            'oborudovanie_po_okved': первое(b.get('equip_by_okved'),
                                            k.get('equipment')),
        }
        # ОКВЭДы: у чеко код УЖЕ с расшифровкой от первоисточника, поэтому он
        # впереди словаря — словарь подписывает лишь то, что встречалось в базе
        # обзвона, а чеко отдаёт название всегда.
        осн_ч = r.get('okved_main_checko')
        осн = первое(r.get('okved_main'), b.get('okved_main'), k.get('okved_main'),
                     c.get('okved'))
        знач['okved'] = осн_ч or (подписать(осн, словарь) if осн else '')
        все_ч = r.get('okved_all_checko')
        все = первое(r.get('okved_all'), c.get('okved_all'),
                     b.get('okved_all_codes'), k.get('okved_all'))
        знач['okvedy_vse'] = все_ч or (подписать(все, словарь) if все
                                       else знач['okved'])
        знач = {п: в for п, в in знач.items() if в}
        if not знач:
            continue
        for п in знач:
            охват[п] += 1
        источники['requisites' if r else ('база обзвона' if (b or k)
                                          else 'companies')] += 1
        правки.append((инн, знач))

    print(f'\nзаполнится карточек: {len(правки)} из {len(наши)}')
    print('по полям:')
    for п, n in охват.most_common():
        print(f'  {п:24} {n:5}')
    print('главный источник:', источники.most_common())
    прим = next((з for и, з in правки if и == '2635040105'), None)
    if прим:
        print('\nСтаврополькрайводоканал получит:')
        for п, в in прим.items():
            print(f'  {п:24} {str(в)[:80]}')

    if not ПРИМЕНИТЬ or not правки:
        if not ПРИМЕНИТЬ:
            print('\nсухой прогон. Повторить с --apply')
        return
    коп = ЦБ + '.bak-' + str(int(time.time()))
    shutil.copy2(ЦБ, коп)
    print(f'бэкап: {os.path.basename(коп)}')
    cx = sqlite3.connect(ЦБ, timeout=120)
    cx.execute('PRAGMA busy_timeout=120000')
    for новая in ('okvedy_vse', 'istochnik_rekvizitov', 'fin_god', 'ssch_god',
                  'telefony_checko', 'pochty_checko'):
        if новая not in кол:
            try:
                cx.execute(f'ALTER TABLE company ADD COLUMN {новая} TEXT')
                print(f'добавлена колонка {новая}')
            except Exception as ex:  # noqa: BLE001
                print(f'колонка {новая}: {str(ex)[:80]}')
    # колонки перечитываем ПОСЛЕ ALTER, иначе новые okvedy_vse не попадут
    живые = {c[1] for c in cx.execute('PRAGMA table_info(company)')}
    n = 0
    for инн, знач in правки:
        поля = [п for п in знач if п in живые]
        if not поля:
            continue
        sql = 'UPDATE company SET ' + ', '.join(f'{п}=?' for п in поля) + \
              ', istochnik_rekvizitov=? WHERE inn=?'
        cx.execute(sql, [знач[п] for п in поля] + ['заливка реквизитов 1с', инн])
        n += 1
    cx.commit()
    прочитано = cx.execute(
        "SELECT COUNT(*) FROM company WHERE COALESCE(okved,'')<>''").fetchone()[0]
    рег = cx.execute(
        "SELECT COUNT(*) FROM company WHERE COALESCE(region,'')<>''").fetchone()[0]
    сайт = cx.execute(
        "SELECT COUNT(*) FROM company WHERE COALESCE(sayt,'')<>''").fetchone()[0]
    cx.close()
    print(json.dumps({'обновлено_карточек': n, 'с_ОКВЭД_в_базе': прочитано,
                      'с_регионом': рег, 'с_сайтом': сайт}, ensure_ascii=False))


if __name__ == '__main__':
    main()
