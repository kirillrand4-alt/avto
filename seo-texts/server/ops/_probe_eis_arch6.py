# -*- coding: utf-8 -*-
r"""ПРОБА 6: rss.html глотает фильтр по заказчику — а results.html?

Гипотеза после пробы 5: RSS-эндпоинт ЕИС понимает узкий набор параметров и всё
незнакомое молча выбрасывает, отдавая общую ленту страны. Тогда фильтр по
организации может работать на ОБЫЧНОЙ странице выдачи (results.html), а нам
останется разобрать ссылки из HTML вместо RSS.

Смотрим:
  1) что за ссылки на «закупки организации» ЕИС кладёт на карточку самой
     организации — это самый честный источник правильного адреса;
  2) отдаёт ли results.html?customerIdOrg=<agencyId> РАЗНЫЕ наборы извещений
     для разных компаний (если наборы совпадают — фильтр снова игнорируется).
"""
import json
import re
import sys
import time

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402

ЦЕЛИ = [('3528000597', '21915'), ('7721632827', '15237')]
ЭТАПЫ = '&fz44=on&fz223=on&af=on&ca=on&pc=on&pa=on&recordsPerPage=_50'


def номера(h):
    """Регистрационные номера извещений со страницы выдачи."""
    return list(dict.fromkeys(re.findall(r'regNumber=(\d{11,25})', h or '')))


def main():
    out = []
    print('НАЧАЛО проба6', flush=True)
    наборы = {}
    for inn, aid in ЦЕЛИ:
        з = {'inn': inn, 'agencyId': aid}
        # 1) карточка организации: какие ссылки на закупки она предлагает
        try:
            h = EC._eis_get('https://zakupki.gov.ru/epz/organization/view223/'
                            'info.html?agencyId=' + aid)
            ссылки = [x.replace('&amp;', '&') for x in
                      re.findall(r'href="([^"]*(?:extendedsearch|search)[^"]*)"', h)]
            з['ссылки_на_закупки'] = list(dict.fromkeys(ссылки))[:8]
            з['инн_на_карточке'] = inn in re.sub(r'<[^>]+>', ' ', h)
        except Exception as ex:  # noqa: BLE001
            з['карточка_ошибка'] = f'{type(ex).__name__}: {str(ex)[:60]}'
        time.sleep(1.0)
        # 2) HTML-выдача с фильтром по организации
        for имя_п in ('customerIdOrg', 'organizationIdList'):
            u = ('https://zakupki.gov.ru/epz/order/extendedsearch/results.html?'
                 + имя_п + '=' + aid + ЭТАПЫ)
            try:
                h = EC._eis_get(u)
                н = номера(h)
                з['html_' + имя_п] = {'байт': len(h), 'номеров': len(н),
                                      'первые': н[:3]}
                наборы[(inn, имя_п)] = set(н[:30])
                # есть ли на странице название/ИНН нашей компании
                т = re.sub(r'<[^>]+>', ' ', h)
                з['html_' + имя_п]['инн_на_странице'] = inn in т
            except Exception as ex:  # noqa: BLE001
                з['html_' + имя_п] = f'{type(ex).__name__}: {str(ex)[:50]}'
            time.sleep(1.0)
        out.append(з)
        print('… ' + json.dumps(з, ensure_ascii=False)[:800], flush=True)
    # РЕШАЮЩИЙ ПРИЗНАК: совпадают ли наборы у двух разных компаний
    for имя_п in ('customerIdOrg', 'organizationIdList'):
        a = наборы.get((ЦЕЛИ[0][0], имя_п)) or set()
        b = наборы.get((ЦЕЛИ[1][0], имя_п)) or set()
        print('ПЕРЕСЕЧЕНИЕ %s: %d из %d/%d' % (имя_п, len(a & b), len(a), len(b)),
              flush=True)
    print('ИТОГ ' + json.dumps(out, ensure_ascii=False, indent=1)[:6000], flush=True)


if __name__ == '__main__':
    main()
