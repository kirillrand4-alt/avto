# -*- coding: utf-8 -*-
"""Живой ли поиск ЕИС: сверяем RSS и HTML на компании, по которой карточки БЫЛИ.

Пустой RSS пришёл сразу по всем эндпоинтам, включая поиск извещений — тот, на
котором держится весь наш путь в ЕИС. Если он молча отдаёт ноль, то все
сегодняшние «в ЕИС пусто» означают не отсутствие закупок, а сломанный поиск, и
их нельзя записывать в замеры.

Берём ИНН, по которым в базе УЖЕ есть контакты с источником zakupki:eis, —
значит когда-то поиск по ним работал.
"""
import json
import re
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402
import enrich_db as EDB       # noqa: E402

e = EDB.EnrichDB().cx


def main():
    инны = [a for a in sys.argv[1:] if a.isdigit()]
    if not инны:
        инны = [r[0] for r in e.execute(
            "SELECT DISTINCT inn FROM phone_contacts WHERE source LIKE 'zakupki%' "
            "LIMIT 3")]
    out = {'проверяем': инны, 'строки': []}
    for inn in инны:
        было = e.execute("SELECT COUNT(*) FROM phone_contacts WHERE inn=? AND "
                         "source LIKE 'zakupki%'", (inn,)).fetchone()[0]
        зап = {'инн': inn, 'контактов_из_еис_в_базе': было}
        # 1. RSS извещений — наш боевой путь
        try:
            h = EC._eis_get(
                'https://zakupki.gov.ru/epz/order/extendedsearch/rss.html?'
                'searchString=' + inn + '&fz44=on&fz223=on&af=on&ca=on&pc=on&pa=on'
                '&recordsPerPage=_50&sortBy=UPDATE_DATE')
            зап['rss_байт'] = len(h)
            зап['rss_items'] = len(re.findall(r'<item>', h))
        except Exception as ex:  # noqa: BLE001
            зап['rss'] = f'{type(ex).__name__}: {str(ex)[:70]}'
        # 2. HTML той же выдачи
        try:
            h2 = EC._eis_get(
                'https://zakupki.gov.ru/epz/order/extendedsearch/results.html?'
                'searchString=' + inn + '&fz44=on&fz223=on&af=on&ca=on&pc=on&pa=on'
                '&recordsPerPage=_10')
            зап['html_байт'] = len(h2)
            номера = sorted(set(re.findall(r'regNumber=(\d{11,25})', h2)))
            зап['html_номеров_закупок'] = len(номера)
            зап['примеры_номеров'] = номера[:3]
            m = re.search(r'Найдено\s*([\d\s]{1,12})', re.sub(r'<[^>]+>', ' ', h2))
            зап['подпись_найдено'] = (m.group(1).strip() if m else '')
        except Exception as ex:  # noqa: BLE001
            зап['html'] = f'{type(ex).__name__}: {str(ex)[:70]}'
        out['строки'].append(зап)
    print(json.dumps(out, ensure_ascii=False, indent=1)[:4000])


if __name__ == '__main__':
    main()
