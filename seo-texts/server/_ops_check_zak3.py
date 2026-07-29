# -*- coding: utf-8 -*-
"""Разведка №9: ищет ли ЕИС по ИНН ПОСТАВЩИКА вообще.

Подозрение из прошлого замера: у Ростелекома нашлось 7 контрактов не потому,
что ЕИС умеет фильтровать по ИНН поставщика, а потому что его ИНН буквально
входит в НОМЕР контракта («Контракт № 7707049388_272143001_...»). У КАМАЗа
тот же запрос дал 0 — хотя контракты у него есть. Если так, «70 компаний ->
1 контракт» меряет не рынок, а совпадение подстроки.
"""
import json
import re
import sys
import time
import traceback

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402


def p(*a):
    print(*a)
    sys.stdout.flush()


def rss(u):
    try:
        t = EC._eis_get(u, timeout=40)
    except Exception as ex:  # noqa: BLE001
        return None, f'{type(ex).__name__}: {str(ex)[:50]}', []
    if not re.search(r'<(?:rss|channel)\b', t or '', re.I):
        return None, 'не RSS (%d б)' % len(t or ''), []
    items = re.findall(r'<item>(.*?)</item>', t, re.S)
    ссылки = []
    for it in items[:3]:
        m = re.search(r'<link>\s*(\S+?)\s*</link>', it, re.S)
        if m:
            v = m.group(1)
            ссылки.append('https://zakupki.gov.ru' + v if v.startswith('/') else v)
    return items, 'ок', ссылки


Б44 = 'https://zakupki.gov.ru/epz/contract/search/rss.html?'
Б223 = 'https://zakupki.gov.ru/epz/contractfz223/search/rss.html?'


def main():
    for arg in sys.argv[1:]:
        inn, _, имя = arg.partition('|')
        p('===== ', inn, имя)
        варианты = [
            ('44 searchString(инн)', Б44 + 'searchString=' + inn + '&morphology=on&fz44=on&recordsPerPage=_50'),
            ('44 supplierTitle(инн)', Б44 + 'supplierTitle=' + inn + '&fz44=on&recordsPerPage=_50'),
            ('44 supplierInn', Б44 + 'supplierInn=' + inn + '&fz44=on&recordsPerPage=_50'),
            ('223 supplierTitle(инн)', Б223 + 'supplierTitle=' + inn + '&recordsPerPage=_50'),
            ('223 searchString(инн)', Б223 + 'searchString=' + inn + '&recordsPerPage=_50'),
        ]
        if имя:
            import urllib.parse
            q = urllib.parse.quote(имя)
            варианты.append(('44 supplierTitle(имя)', Б44 + 'supplierTitle=' + q
                             + '&fz44=on&recordsPerPage=_50'))
            варианты.append(('44 searchString(имя)', Б44 + 'searchString=' + q
                             + '&morphology=on&fz44=on&recordsPerPage=_50'))
        лучш = None
        for метка, u in варианты:
            items, сост, сс = rss(u)
            n = len(items) if items is not None else -1
            p('  %-24s items=%-4s %s' % (метка, n, сост))
            if n > 0 and лучш is None and 'supplierTitle' in u:
                лучш = (метка, сс)
            time.sleep(0.8)
        # проверяем, что найденное ДЕЙСТВИТЕЛЬНО про нашего поставщика
        if лучш and лучш[1]:
            u = лучш[1][0]
            try:
                h = EC._eis_get(u, timeout=40)
                t = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', h))
                m = re.search(r'(?:Поставщик|поставщик\w*)(.{0,600})', t)
                p('  СВЕРКА %s: инн_на_карточке=%s' % (лучш[0], inn in t))
                p('  КУСОК:', (m.group(1)[:330] if m else t[:250]))
            except Exception as ex:  # noqa: BLE001
                p('  сверка ОШИБКА', type(ex).__name__, str(ex)[:50])
    p('ИТОГ: вариантов поиска проверено на %d ИНН' % (len(sys.argv) - 1))


if __name__ == '__main__':
    try:
        main()
    except Exception:  # noqa: BLE001
        p('ФАТАЛЬНО:', traceback.format_exc()[-500:])
