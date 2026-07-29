# -*- coding: utf-8 -*-
"""Что отдаёт реестр контрактов ЕИС на поиск по ИНН поставщика.

Обратный ход дал ноль контрактов на шести компаниях и НОЛЬ ошибок — значит
ответ пришёл, но пустой. Разница принципиальная: либо у этих компаний правда
нет госконтрактов, либо мы стучимся не туда. Печатаем сырьё.
"""
import json
import re
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402

ВАРИАНТЫ = (
    ('rss контрактов',
     'https://zakupki.gov.ru/epz/contract/search/rss.html?searchString={inn}'),
    ('rss контрактов + этапы',
     'https://zakupki.gov.ru/epz/contract/search/rss.html?searchString={inn}'
     '&morphology=on&fz44=on&contractStageList_0=on&contractStageList_1=on'
     '&contractStageList_2=on&contractStageList_3=on&recordsPerPage=_50'),
    ('html поиска контрактов',
     'https://zakupki.gov.ru/epz/contract/search/results.html?searchString={inn}'
     '&morphology=on&fz44=on&recordsPerPage=_10'),
    ('rss извещений (для сравнения)',
     'https://zakupki.gov.ru/epz/order/extendedsearch/rss.html?searchString={inn}'
     '&fz44=on&fz223=on&af=on&ca=on&pc=on&pa=on&recordsPerPage=_50'),
)


def main():
    инны = [a for a in sys.argv[1:] if a.isdigit()] or ['5001000066']
    out = []
    for inn in инны:
        for имя, шаблон in ВАРИАНТЫ:
            зап = {'инн': inn, 'вариант': имя}
            try:
                h = EC._eis_get(шаблон.format(inn=inn))
                зап['байт'] = len(h)
                зап['похоже_на_rss'] = bool(re.search(r'<(?:rss|channel)\b', h, re.I))
                зап['items'] = len(re.findall(r'<item>', h))
                зап['есть_реестровый_номер'] = bool(
                    re.search(r'reestrNumber|contractCard', h))
                зап['начало'] = re.sub(r'\s+', ' ', h)[:220]
            except Exception as ex:  # noqa: BLE001
                зап['ошибка'] = f'{type(ex).__name__}: {str(ex)[:90]}'
            out.append(зап)
    print(json.dumps(out, ensure_ascii=False, indent=1)[:5000])


if __name__ == '__main__':
    main()
