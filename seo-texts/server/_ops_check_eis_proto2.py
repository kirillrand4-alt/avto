# -*- coding: utf-8 -*-
"""Вкладка «Протоколы»: пусто ВСЕГДА или только у свежих незавершённых закупок.

Первый заход: вкладка «Протоколы» есть у КАЖДОЙ карточки, боевой код её не
открывает. Но четыре открытых вкладки дали ноль файлов — и это ожидаемо, я взял
самые свежие извещения (RSS сортирован по дате обновления), где торги ещё идут.
Честная проверка требует ЗАВЕРШЁННЫХ закупок. Берём много регномеров сразу,
без открытия карточек (экономим запросы), и смотрим на самой вкладке: что
написано текстом и какие ссылки есть.

Запуск: python _ops_check_eis_proto2.py [ИНН ...]
"""
import json
import re
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402

_КОМ = re.compile(r'председател\w*\s+комисси|член\w*\s+комисси|секретар\w*\s+комисси'
                  r'|состав\w*\s+комисси|протокол\w*\s+заседани|заседани\w*\s+комисси'
                  r'|присутствовал', re.I)


def текст(h):
    h = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', h, flags=re.S | re.I)
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', h))


def регномера(inn):
    try:
        rss = EC._eis_get(
            'https://zakupki.gov.ru/epz/order/extendedsearch/rss.html?searchString='
            + inn + '&fz44=on&fz223=on&af=on&ca=on&pc=on&pa=on'
            + '&recordsPerPage=_50&sortBy=UPDATE_DATE')
    except Exception as ex:  # noqa: BLE001
        return [], f'{type(ex).__name__}'
    из = []
    for m in re.finditer(r'<link>\s*(\S+?)\s*</link>', rss):
        u = m.group(1)
        rm = re.search(r'regNumber=(\d+)', u)
        if rm and rm.group(1) not in из:
            из.append(rm.group(1))
    return из, ''


def main():
    буф = []

    def P(s):
        буф.append(str(s))

    инны = [a for a in sys.argv[1:] if a.isdigit()] or ['7424024375', '3801098402']
    итог = {'вкладок_открыто': 0, 'вкладок_с_файлами': 0, 'файлов': 0,
            'прочитано': 0, 'с_составом_комиссии': 0}
    примеры = []
    for inn in инны[:2]:
        рег, ош = регномера(inn)
        P(f'=== ИНН {inn}: регномеров={len(рег)} {ош}')
        # берём и свежие, и ХВОСТ списка (старые/завершённые)
        выбор = рег[:4] + рег[-8:]
        видел = set()
        for rn in выбор:
            if rn in видел:
                continue
            видел.add(rn)
            u = ('https://zakupki.gov.ru/epz/order/notice/notice223/protocols.html'
                 '?purchaseNoticeNumber=' + rn)
            try:
                h = EC._eis_get(u)
            except Exception as ex:  # noqa: BLE001
                P(f'  {rn}: вкладка не открылась {type(ex).__name__}')
                continue
            итог['вкладок_открыто'] += 1
            t = текст(h)
            файлы = []
            for m2 in re.finditer(
                    r'<a\b[^>]*href="([^"]*filestore[^"]*)"[^>]*>(.*?)</a>', h, re.S):
                имя = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ',
                                                 m2.group(2))).strip()
                ссылка = m2.group(1).replace('&amp;', '&')
                if ссылка.startswith('/'):
                    ссылка = 'https://zakupki.gov.ru' + ссылка
                файлы.append((имя[:70], ссылка))
            прот_сс = sorted(set(re.findall(
                r'href="([^"]*protocol[^"]*)"', h, re.I)))
            прот_сс = [x for x in прот_сс if 'protocols.html' not in x]
            # что вкладка ГОВОРИТ текстом
            i = t.lower().find('протокол')
            фраза = t[max(0, i - 80):i + 220] if i >= 0 else '(слова протокол нет)'
            P(f'  {rn}: html={len(h)} файлов={len(файлы)} подстраниц_протокола='
              f'{len(прот_сс)}')
            P('     текст> ' + фраза)
            if прот_сс:
                P('     подстраницы: ' + json.dumps(
                    [x[:100] for x in прот_сс[:4]], ensure_ascii=False))
            if файлы:
                итог['вкладок_с_файлами'] += 1
                итог['файлов'] += len(файлы)
                P('     имена: ' + json.dumps([n for n, _ in файлы][:8],
                                              ensure_ascii=False))
                примеры += файлы[:2]
    # читаем найденные протоколы
    P('=== ЧТЕНИЕ ПРОТОКОЛОВ ===')
    for имя, сс in примеры[:5]:
        t = EC.doc_text(сс)
        итог['прочитано'] += 1
        P(f'  «{имя}» символов={len(t or "")} ссылка={сс[-60:]}')
        if not t:
            P('     ПУСТО (doc_text вернул ничего)')
            continue
        m = _КОМ.search(t)
        if m:
            итог['с_составом_комиссии'] += 1
            P('     КОМИССИЯ> ' + re.sub(
                r'\s+', ' ', t[max(0, m.start() - 300):m.start() + 800]))
        else:
            P('     начало> ' + re.sub(r'\s+', ' ', t)[:300])
    print('\n'.join(буф)[-11500:])
    print('ИТОГ ' + json.dumps(итог, ensure_ascii=False))


if __name__ == '__main__':
    main()
