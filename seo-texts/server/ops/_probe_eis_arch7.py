# -*- coding: utf-8 -*-
r"""ПРОБА 7: реестр КОНТРАКТОВ как вход к закупкам конкретного заказчика.

Что уже отвергнуто: `customerTitle` на поиске извещений, `customerIdOrg` и
`organizationIdList` и на rss.html, и на results.html — все три ЕИС молча
игнорирует и отдаёт общую ленту страны (пересечение наборов у двух разных
компаний 30 из 30).

Осталась одна зацепка: на реестрах КОНТРАКТОВ фильтр по стороне сделки
доказанно работает — `supplierTitle` в find_zakupki_supplier ищет именно
нужного поставщика. Значит на том же эндпоинте должен работать и
`customerTitle`. Если работает — из карточки контракта берём номер извещения,
а по номеру собираем адрес карточки закупки, где и лежит контактный блок.

Признак работающего фильтра: у двух разных компаний РАЗНЫЕ наборы и на
карточке стоит ИНН нужной.
"""
import json
import re
import sys
import time

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402

ЦЕЛИ = ['3528000597', '7721632827']
АДРЕСА = {
    'фз223_customerTitle':
        'https://zakupki.gov.ru/epz/contractfz223/search/rss.html?'
        'customerTitle={inn}&recordsPerPage=_50',
    'фз44_customerTitle':
        'https://zakupki.gov.ru/epz/contract/search/rss.html?customerTitle={inn}'
        '&contractStageList_0=on&contractStageList_1=on&contractStageList_2=on'
        '&contractStageList_3=on&recordsPerPage=_50',
}


def ссылки_rss(url):
    try:
        r = EC._eis_get(url)
    except Exception as ex:  # noqa: BLE001
        return None, f'{type(ex).__name__}: {str(ex)[:45]}'
    if not re.search(r'<(?:rss|channel)\b', r or '', re.I):
        return None, 'не RSS'
    из = []
    for it in re.findall(r'<item>(.*?)</item>', r, re.S):
        lm = re.search(r'<link>\s*(\S+?)\s*</link>', it, re.S)
        dm = re.search(r'<pubDate>\s*(.*?)\s*</pubDate>', it, re.S)
        if lm:
            u = lm.group(1)
            # в RSS контрактов ссылка ОТНОСИТЕЛЬНАЯ — ловушка 6.5 передачи
            if u.startswith('/'):
                u = 'https://zakupki.gov.ru' + u
            из.append((u, (dm.group(1)[:16] if dm else '')))
    return из, ''


def main():
    out, наборы = [], {}
    print('НАЧАЛО проба7', flush=True)
    for inn in ЦЕЛИ:
        з = {'inn': inn}
        for имя, шаб in АДРЕСА.items():
            сс, err = ссылки_rss(шаб.format(inn=inn))
            if сс is None:
                з[имя] = {'ошибка': err}
                continue
            з[имя] = {'позиций': len(сс), 'первые_даты': [d for _u, d in сс[:3]],
                      'последняя_дата': (сс[-1][1] if сс else '')}
            наборы[(inn, имя)] = {u for u, _d in сс[:30]}
            # открываем первую карточку и проверяем, наш ли это заказчик
            if сс:
                try:
                    h = EC._eis_get(сс[0][0])
                    t = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', h))
                    з[имя]['инн_на_карточке'] = inn in t
                    з[имя]['url'] = сс[0][0][:100]
                    # номер извещения на карточке контракта — вход к закупке
                    ном = re.findall(r'(?:извещени\w*|закупк\w*)\D{0,40}(\d{11,25})',
                                     t, re.I)
                    з[имя]['номера_извещений'] = list(dict.fromkeys(ном))[:3]
                    зм = re.search(r'Заказчик\s*[:\-]?\s*([^,;]{6,90})', t)
                    з[имя]['заказчик'] = (зм.group(1).strip() if зм else '')
                except Exception as ex:  # noqa: BLE001
                    з[имя]['карточка_ошибка'] = f'{type(ex).__name__}: {str(ex)[:45]}'
            time.sleep(1.0)
        out.append(з)
        print('… ' + json.dumps(з, ensure_ascii=False)[:700], flush=True)
    for имя in АДРЕСА:
        a = наборы.get((ЦЕЛИ[0], имя)) or set()
        b = наборы.get((ЦЕЛИ[1], имя)) or set()
        print('ПЕРЕСЕЧЕНИЕ %s: %d при наборах %d/%d' % (имя, len(a & b), len(a), len(b)),
              flush=True)
    print('ИТОГ ' + json.dumps(out, ensure_ascii=False, indent=1)[:5000], flush=True)


if __name__ == '__main__':
    main()
