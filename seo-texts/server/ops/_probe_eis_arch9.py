# -*- coding: utf-8 -*-
r"""ПРОБА 9: уточняем аудит прежнего источника, прежде чем называть это браком.

Аудит показал: у 5 из 12 записей `zakupki:eis` ИНН компании на странице-
источнике не стоит. Возможных объяснения два, и они требуют разных выводов:
  (а) разбор писал контакт с ЧУЖОЙ карточки (или со служебной части страницы);
  (б) карточка за это время просто перестала открываться, и проверять на ней
      уже нечего.
Пока не отличили — обвинять код нельзя.

Что смотрим:
  1) живая ли страница: есть ли на ней блок «Заказчик» и контактный блок;
  2) откуда взялся записанный телефон — из карточки или из подвала ЕИС
     (телефоны техподдержки видны на КАЖДОЙ странице сайта);
  3) сколько в базе записей `zakupki:eis`, где ИМЯ ЧЕЛОВЕКА — это кусок
     вёрстки («Опросы Статистика Карта», «Преимущества Не»). Этот счёт сети не
     требует и сам по себе доказывает брак разбора.
"""
import json
import re
import sys
import time

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402
import enrich_db as EDB       # noqa: E402

ПОДОЗРЕВАЕМЫЕ = [
    ('7734242302', '+7 (499) 9494467',
     'https://zakupki.gov.ru/223/purchase/public/purchase/info/'
     'common-info.html?regNumber=32211269469'),
    ('7817311895', '+7 (499) 9494740',
     'https://zakupki.gov.ru/223/purchase/public/purchase/info/'
     'common-info.html?regNumber=32515459450'),
    ('3801046700', '+7 (499) 499-51-78 доб.888',
     'https://zakupki.gov.ru/223/purchase/public/purchase/info/'
     'common-info.html?regNumber=31908486734'),
]


def main():
    db = EDB.EnrichDB()
    e = db.cx
    out = {'страницы': []}

    # 1) БЕЗ СЕТИ: имена-обрывки вёрстки среди записанных «людей»
    мусор = re.compile(
        r'опрос|статистик|карта сайта|преимуществ|органам контрол|отчет о'
        r'|главная|версия для|личный кабинет|обратная связь', re.I)
    всего = e.execute("SELECT COUNT(*) FROM phone_contacts "
                      "WHERE source='zakupki:eis'").fetchone()[0]
    строки = list(e.execute(
        "SELECT inn, person, phone, source_url FROM phone_contacts "
        "WHERE source='zakupki:eis'"))
    битые = [r for r in строки if r[1] and мусор.search(r[1])]
    out['zakupki_eis_всего'] = всего
    out['имя_это_вёрстка'] = len(битые)
    out['примеры_битых'] = [{'инн': r[0], 'кто': r[1], 'тел': r[2]}
                            for r in битые[:6]]
    # частота телефонов: номер, который повторяется у ДЕСЯТКОВ разных ИНН, —
    # это не телефон компании, это телефон самого сайта
    част = {}
    for inn, _p, тел, _u in строки:
        ц = re.sub(r'\D', '', тел or '')[-10:]
        if ц:
            част.setdefault(ц, set()).add(inn)
    топ = sorted(част.items(), key=lambda kv: -len(kv[1]))[:6]
    out['телефон_у_скольких_разных_ИНН'] = [
        {'номер': k, 'компаний': len(v)} for k, v in топ]

    # 2) С СЕТЬЮ: живы ли подозрительные страницы и откуда номер
    for inn, тел, url in ПОДОЗРЕВАЕМЫЕ:
        з = {'инн': inn, 'записанный_тел': тел, 'url': url[-46:]}
        try:
            h = EC._eis_get(url)
            t = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', h))
            з['байт'] = len(h)
            з['есть_блок_Заказчик'] = bool(re.search(r'Заказчик', t))
            з['есть_Контактн'] = bool(re.search(r'Контактн\w+ (?:информац|лиц)', t, re.I))
            з['инн_компании_на_странице'] = inn in t
            з['похоже_на_заглушку'] = bool(
                re.search(r'не найден|отсутству|ошибка|недоступ', t, re.I))
            ц = re.sub(r'\D', '', тел)[-10:]
            з['номер_есть_на_странице'] = ц in re.sub(r'\D', '', t)
            # где именно: в подвале сайта или в карточке
            if з['номер_есть_на_странице']:
                поз = re.sub(r'\D', '', t).find(ц)
                з['доля_позиции_в_тексте'] = round(поз / max(1, len(re.sub(r'\D', '', t))), 2)
            зм = re.search(r'Заказчик\s*[:\-]?\s*([^,;]{6,70})', t)
            з['заказчик'] = (зм.group(1).strip() if зм else '')[:60]
        except Exception as ex:  # noqa: BLE001
            з['ошибка'] = f'{type(ex).__name__}: {str(ex)[:60]}'
        out['страницы'].append(з)
        print('… ' + json.dumps(з, ensure_ascii=False)[:400], flush=True)
        time.sleep(0.8)
    print('ИТОГ9 ' + json.dumps(out, ensure_ascii=False, indent=1)[:4500], flush=True)


if __name__ == '__main__':
    main()
