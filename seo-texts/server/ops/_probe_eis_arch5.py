# -*- coding: utf-8 -*-
r"""ПРОБА 5: как в ЕИС правильно спросить «закупки ЭТОГО заказчика».

Проба 4 показала две неприятности:
  * `customerTitle=` ЕИС МОЛЧА ИГНОРИРУЕТ — у пяти разных компаний первая
    позиция выдачи оказалась одна и та же (regNumber=32616249065), то есть это
    общая лента последних закупок страны. Фильтр, который выглядит как фильтр,
    но не фильтрует, — прямой путь записать чужие контакты нашей компании;
  * `searchString=ИНН` (то, чем пользуется боевой find_zakupki_contacts) у
    крупных заказчиков отдаёт либо ноль (Северсталь, Уралкалий), либо блок
    трёхлетней давности (Росэнергоатом — весь март 2023, Уренгой — март 2022).

Ищем честный фильтр: сперва находим карточку организации в реестре ЕИС по ИНН,
берём её внутренний идентификатор, потом пробуем им отфильтровать извещения.
Признак, что фильтр РАБОТАЕТ, а не игнорируется: выдача у разных компаний
разная И на первой карточке стоит ИНН этой компании.
"""
import json
import re
import sys
import time

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402

ИННЫ = ['3528000597', '7721632827']
МАРКЕР_ОБЩЕЙ_ЛЕНТЫ = '32616249065'
ЭТАПЫ = '&fz44=on&fz223=on&af=on&ca=on&pc=on&pa=on&recordsPerPage=_50'
КОРЕНЬ = 'https://zakupki.gov.ru/epz/order/extendedsearch/rss.html?'


def первая(url):
    try:
        r = EC._eis_get(url)
    except Exception as ex:  # noqa: BLE001
        return {'ошибка': f'{type(ex).__name__}: {str(ex)[:45]}'}
    if not re.search(r'<(?:rss|channel)\b', r or '', re.I):
        return {'не_rss': (r or '')[:60]}
    its = re.findall(r'<item>(.*?)</item>', r, re.S)
    if not its:
        return {'позиций': 0}
    lm = re.search(r'<link>\s*(\S+?)\s*</link>', its[0], re.S)
    u = lm.group(1) if lm else ''
    dm = re.search(r'<pubDate>\s*(.*?)\s*</pubDate>', its[0], re.S)
    return {'позиций': len(its), 'первая': u[-40:],
            'общая_лента': МАРКЕР_ОБЩЕЙ_ЛЕНТЫ in u,
            'дата': (dm.group(1)[:16] if dm else '')}


def main():
    out = []
    print('НАЧАЛО проба5', flush=True)
    for inn in ИННЫ:
        з = {'inn': inn}
        # 1) карточка организации в реестре ЕИС
        u = ('https://zakupki.gov.ru/epz/organization/search/results.html'
             '?searchString=' + inn + '&fz44=on&fz223=on&priz223=on')
        try:
            h = EC._eis_get(u)
            з['реестр_байт'] = len(h)
            ссылки = re.findall(r'href="([^"]*organization/view[^"]*)"', h)
            з['ссылки_орг'] = list(dict.fromkeys(
                x.replace('&amp;', '&') for x in ссылки))[:4]
            ids = {}
            for x in з['ссылки_орг']:
                for k, v in re.findall(r'[?&](\w+)=([^&"]+)', x):
                    ids.setdefault(k, v)
            з['идентификаторы'] = ids
            # ИНН рядом со ссылкой — доказательство, что нашли нужную организацию
            з['инн_в_реестре'] = inn in re.sub(r'<[^>]+>', ' ', h)
        except Exception as ex:  # noqa: BLE001
            з['реестр_ошибка'] = f'{type(ex).__name__}: {str(ex)[:60]}'
            з['идентификаторы'] = {}
        time.sleep(1.0)
        # 2) пробуем отфильтровать извещения найденным идентификатором
        з['попытки'] = {}
        кандидаты = []
        for k, v in (з.get('идентификаторы') or {}).items():
            if k.lower() in ('organizationid', 'agencyid', 'organizationcode'):
                кандидаты += [('customerIdOrg', v), ('organizationIdList', v),
                              ('customerIdOrgList', v)]
        # и вариант «код организации» прямо из ссылки
        for имя_п, зн in кандидаты[:6]:
            з['попытки'][f'{имя_п}={зн[:14]}'] = первая(
                КОРЕНЬ + имя_п + '=' + зн + ЭТАПЫ)
            time.sleep(0.8)
        out.append(з)
        print('… ' + json.dumps(з, ensure_ascii=False)[:900], flush=True)
    print('ИТОГ ' + json.dumps(out, ensure_ascii=False, indent=1)[:7000], flush=True)


if __name__ == '__main__':
    main()
