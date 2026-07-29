# -*- coding: utf-8 -*-
"""ПРОБА 2: открываем СТАРЫЕ карточки и смотрим, что из них реально читается.

Проба 1 показала: pubDate есть у всех позиций RSS, окна publishDateFrom/To
работают, pageNumber — нет. Осталось убедиться в главном:
  * разбор `_eis_people` не разваливается на карточках трёх-четырёхлетней
    давности (вёрстка ЕИС за эти годы менялась);
  * предмет закупки со страницы читается (в заголовке RSS его нет);
  * НАШ ИНН на странице действительно есть — это доказательство привязки,
    без него карточку брать нельзя (правило дня: рубеж закрыт по умолчанию);
  * не подсовывает ли ЕИС контакт УПОЛНОМОЧЕННОГО ОРГАНА вместо заказчика —
    тогда человек работает в министерстве, а не на заводе.
"""
import json
import re
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402

ИННЫ = ['9719079775', '9704016606', '9102157783', '9102016743']
БАЗА = ('https://zakupki.gov.ru/epz/order/extendedsearch/rss.html?searchString='
        '{inn}&fz44=on&fz223=on&af=on&ca=on&pc=on&pa=on&recordsPerPage=_50')


def дата(it):
    m = re.search(r'<pubDate>\s*(.*?)\s*</pubDate>', it, re.S)
    if not m:
        return None
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(m.group(1)).astimezone(timezone.utc).date()
    except Exception:  # noqa: BLE001
        return None


def main():
    сег = datetime.now(timezone.utc).date()
    out = {'проба': 'eis-arch-2', 'карточки': []}
    print('НАЧАЛО', flush=True)
    for inn in ИННЫ:
        # окно «два-три года назад» — ровно та зона, ради которой всё затевалось
        u = (БАЗА.format(inn=inn) + '&publishDateFrom='
             + (сег.replace(year=сег.year - 3)).strftime('%d.%m.%Y')
             + '&publishDateTo=' + (сег.replace(year=сег.year - 2)).strftime('%d.%m.%Y'))
        try:
            rss = EC._eis_get(u)
        except Exception as ex:  # noqa: BLE001
            out['карточки'].append({'inn': inn, 'ошибка_rss': str(ex)[:70]})
            continue
        items = re.findall(r'<item>(.*?)</item>', rss, re.S)
        if not items:
            out['карточки'].append({'inn': inn, 'позиций_в_окне': 0})
            continue
        взято = 0
        for it in items:
            if взято >= 2:
                break
            lm = re.search(r'<link>\s*(\S+?)\s*</link>', it, re.S)
            if not lm:
                continue
            url = lm.group(1)
            if url.startswith('/'):
                url = 'https://zakupki.gov.ru' + url
            d = дата(it)
            r = {'inn': inn, 'url': url[:120],
                 'дата': (d.isoformat() if d else ''),
                 'возраст_дней': ((сег - d).days if d else None)}
            try:
                h = EC._eis_get(url)
                txt = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', re.sub(
                    r'<(script|style)[^>]*>.*?</\1>', ' ', h, flags=re.S | re.I)))
                r['длина_текста'] = len(txt)
                r['инн_на_странице'] = inn in txt
                пм = re.search(r'(?:Наименование|Предмет|Объект)\s+(?:закуп\w+|'
                               r'договор\w+|контракт\w+)\s*[:\-]?\s*(.{6,220})',
                               txt, re.I)
                r['предмет'] = (пм.group(1).strip()[:120] if пм else '')
                r['люди'] = EC._eis_people(txt)[:4]
                # посредник: уполномоченный орган / специализированная организация
                пос = re.search(r'(Уполномоченн\w+\s+(?:орган|учрежден\w+)|'
                                r'Специализированн\w+\s+организац\w+|'
                                r'Организац\w+,?\s+осуществляющ\w+\s+размещен\w+)'
                                r'(.{0,300})', txt, re.I)
                if пос:
                    r['посредник_блок'] = re.sub(r'\s+', ' ', пос.group(0))[:200]
                # где стоит контактный блок и какие ИНН рядом
                кб = re.search(r'Контактн\w+\s+информаци\w+(.{0,900})', txt, re.I)
                if кб:
                    r['контактблок'] = кб.group(1)[:330]
                    r['инн_рядом'] = re.findall(r'(?<!\d)(\d{10}|\d{12})(?!\d)',
                                                txt[:max(0, кб.start())][-1500:])[-3:]
            except Exception as ex:  # noqa: BLE001
                r['ошибка'] = f'{type(ex).__name__}: {str(ex)[:60]}'
            out['карточки'].append(r)
            взято += 1
            print('… ' + json.dumps(r, ensure_ascii=False)[:500], flush=True)
            time.sleep(1.2)
    print('ИТОГ ' + json.dumps(out, ensure_ascii=False, indent=1)[:9000], flush=True)


if __name__ == '__main__':
    main()
