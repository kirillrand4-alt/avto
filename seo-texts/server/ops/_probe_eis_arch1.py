# -*- coding: utf-8 -*-
"""ПРОБА 1 архивного прохода по ЕИС: отдаёт ли поиск СТАРЫЕ процедуры и видна
ли дата.

Проверяем на компаниях, по которым карточки ЗАВЕДОМО находились раньше
(ловушка 4.8 передачи: пустой ответ ≠ сломанный источник, проверять надо на
том, что работало). Список берём из потоков прошлых прогонов ЕИС.

Что смотрим:
  1) есть ли в <item> RSS дата (pubDate) — тогда дату можно брать БЕЗ открытия
     карточки, это в разы дешевле;
  2) работает ли постраничный обход (pageNumber) — то есть можно ли достать
     больше 50 карточек;
  3) работает ли фильтр по датам публикации (publishDateFrom/publishDateTo) —
     то есть можно ли адресно копать по годам.
Ничего не пишет в базу: это разведка.
"""
import io
import json
import os
import re
import sys
import time

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402

ПОТОКИ = [r'C:\seostat\drop\sales_eis_stream.jsonl',
          r'C:\seostat\drop\core_eis_stream.jsonl']


def кандидаты(n=4):
    """ИНН, у которых прошлый прогон РЕАЛЬНО видел карточки."""
    из = []
    for п in ПОТОКИ:
        if not os.path.exists(п):
            continue
        for ln in io.open(п, encoding='utf-8', errors='replace'):
            try:
                d = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            if d.get('rss_items') and (d.get('cards') or []):
                из.append((int(d['rss_items']), d['inn']))
    из.sort(reverse=True)
    вид, рез = set(), []
    for _n, i in из:
        if i not in вид:
            вид.add(i)
            рез.append(i)
        if len(рез) >= n:
            break
    return рез


БАЗА = ('https://zakupki.gov.ru/epz/order/extendedsearch/rss.html?searchString='
        '{inn}&fz44=on&fz223=on&af=on&ca=on&pc=on&pa=on&recordsPerPage=_50')


def позиции(url):
    try:
        rss = EC._eis_get(url)
    except Exception as ex:  # noqa: BLE001
        return None, f'{type(ex).__name__}: {str(ex)[:60]}'
    if not re.search(r'<(?:rss|channel)\b', rss or '', re.I):
        return None, 'не RSS (заглушка/лимит), первые 120: ' + (rss or '')[:120]
    return re.findall(r'<item>(.*?)</item>', rss, re.S), ''


def дата_из_item(it):
    m = re.search(r'<pubDate>\s*(.*?)\s*</pubDate>', it, re.S)
    return m.group(1) if m else ''


def main():
    инны = кандидаты(4)
    out = {'проба': 'eis-arch-1', 'инны': инны, 'по_компаниям': []}
    print('НАЧАЛО ' + json.dumps({'инны': инны}, ensure_ascii=False), flush=True)
    for inn in инны:
        r = {'inn': inn}
        items, err = позиции(БАЗА.format(inn=inn) + '&sortBy=UPDATE_DATE')
        if items is None:
            r['ошибка_стр1'] = err
            out['по_компаниям'].append(r)
            continue
        r['стр1_позиций'] = len(items)
        даты = [дата_из_item(x) for x in items]
        r['есть_pubDate'] = sum(1 for d in даты if d)
        r['примеры_дат'] = [d for d in даты if d][:3]
        # заголовок первой позиции — подтверждаем, что предмета в нём нет
        tm = re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>',
                       items[0], re.S) if items else None
        r['первый_title'] = re.sub(r'\s+', ' ', tm.group(1))[:110] if tm else ''
        lm = re.search(r'<link>\s*(\S+?)\s*</link>', items[0], re.S) if items else None
        r['первый_link'] = (lm.group(1) if lm else '')[:110]
        time.sleep(1.0)
        # СТРАНИЦА 2 — можно ли выйти за 50
        it2, err2 = позиции(БАЗА.format(inn=inn) + '&sortBy=UPDATE_DATE&pageNumber=2')
        r['стр2_позиций'] = len(it2) if it2 is not None else err2[:70]
        if it2:
            л1 = {re.search(r'<link>\s*(\S+?)\s*</link>', x, re.S).group(1)
                  for x in items if re.search(r'<link>', x)}
            л2 = {re.search(r'<link>\s*(\S+?)\s*</link>', x, re.S).group(1)
                  for x in it2 if re.search(r'<link>', x)}
            r['стр2_новых'] = len(л2 - л1)
            r['стр2_даты'] = [d for d in (дата_из_item(x) for x in it2) if d][:3]
        time.sleep(1.0)
        # ФИЛЬТР ПО ДАТАМ — окно позапрошлого года
        u = (БАЗА.format(inn=inn)
             + '&publishDateFrom=01.01.2024&publishDateTo=31.12.2024')
        it3, err3 = позиции(u)
        r['2024_позиций'] = len(it3) if it3 is not None else err3[:70]
        if it3:
            r['2024_даты'] = [d for d in (дата_из_item(x) for x in it3) if d][:3]
        time.sleep(1.0)
        u = (БАЗА.format(inn=inn)
             + '&publishDateFrom=01.01.2021&publishDateTo=31.12.2021')
        it4, err4 = позиции(u)
        r['2021_позиций'] = len(it4) if it4 is not None else err4[:70]
        if it4:
            r['2021_даты'] = [d for d in (дата_из_item(x) for x in it4) if d][:3]
        out['по_компаниям'].append(r)
        print('… ' + json.dumps(r, ensure_ascii=False)[:400], flush=True)
        time.sleep(1.0)
    print('ИТОГ ' + json.dumps(out, ensure_ascii=False, indent=1)[:6000], flush=True)


if __name__ == '__main__':
    main()
