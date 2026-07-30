# -*- coding: utf-8 -*-
"""Замер: что лежит в карточках Tender.pro, которые НЕ отдавались провайдеру.

Отбор в `tenderpro_lica.py` шёл по двум механическим признакам: есть телефон
(`telefony_razmetka` + `telefony_tekst`) ИЛИ есть техническое слово (`est_teh`).
Остальные не читались вовсе. Здесь считаю со знаменателем, что в них есть.

Правило владельца №4: считаю карточки И компании (company_id), а не только строки.
"""
import csv
import os
import re
import sys

BAZA = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BAZA, 'engineers-lens', 'centro', 'tenderpro')
KART = os.path.join(OUT, 'tp-kartochki.csv')

# «Фамилия И.О.» / «Фамилия И. О.»
FIO_INIC = re.compile(r'[А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ]\.\s?[А-ЯЁ]\.')
# «И.О. Фамилия»
INIC_FIO = re.compile(r'[А-ЯЁ]\.\s?[А-ЯЁ]\.\s*[А-ЯЁ][а-яё]{2,}')
# два-три слова с заглавной подряд (Волков Максим Валерьевич / Александр Владимирович Лосев)
FIO_POLN = re.compile(r'[А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ][а-яё]{2,}(?:\s+[А-ЯЁ][а-яё]{2,})?')
POCHTA = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')

# слова о должности — шире, чем est_teh: сюда входят и нетехнические должности,
# потому что «есть слово о должности» и «техническая должность» — разные величины
DOLZH = re.compile(
    r'главн\w*\s+(?:инженер|механик|энергетик|метролог|технолог)|'
    r'\bинженер|\bмеханик|\bэнергетик|\bметролог|\bтехнолог|'
    r'начальник|заместитель|\bзам\.|директор|руководитель|мастер\b|'
    r'специалист|менеджер|куратор|диспетчер|экономист|бухгалтер|юрист|'
    r'снабжен|закупк|ОМТС|ОГМ|ОГЭ|КИПиА|КИП\s?и\s?А|ОТиР|ТОиР', re.I)

# технические слова — тот же смысл, что est_teh, но проверяю своим набором,
# чтобы увидеть, не разошёлся ли флаг из выгрузки с содержимым
TEH = re.compile(
    r'техн|главн\w*\s+(?:инженер|механик|энергетик)|инженер|механик|энергетик|'
    r'ОГМ|ОГЭ|КИПиА|эксплуатац|компрессорн\w*\s+(?:станц|цех)', re.I)

# «мусорные» заглавные пары, которые ловит FIO_POLN, но человеком не являются
MUSOR = re.compile(
    r'^(?:Российск|Гражданск|Федеральн|Обществ|Закрыт|Открыт|Публичн|Акционерн|'
    r'Ограничен|Единый|Электронн|Торгов|Запрос|Коммерческ|Техническ|Приложен|'
    r'Договор|Заказчик|Организатор|Участник|Победител|Комисси|Республик|Област|'
    r'Настоящ|Данн|Указан|Извещен|Документ|Протокол|Поставк|Услуг|Работ|Товар)')


def est_fio(s):
    """Есть ли похожее на человека. Возвращает список найденных строк."""
    naideno = []
    naideno += FIO_INIC.findall(s)
    naideno += INIC_FIO.findall(s)
    for m in FIO_POLN.findall(s):
        if MUSOR.match(m):
            continue
        naideno.append(m)
    return naideno


def main():
    vse = 0
    otsech = []          # карточки, НЕ попавшие в разбор
    vzyato = 0
    for r in csv.DictReader(open(KART, encoding='utf-8-sig'), delimiter=';'):
        vse += 1
        tel = (r.get('telefony_razmetka') or '') + (r.get('telefony_tekst') or '')
        if tel or r.get('est_teh'):
            vzyato += 1
        else:
            otsech.append(r)

    n = len(otsech)
    print(f'карточек всего в файле: {vse}')
    print(f'отдавалось провайдеру (телефон ИЛИ техслово): {vzyato}')
    print(f'ОТСЕЧЕНО (знаменатель дальше): {n}')
    print()

    sch = {k: 0 for k in ('comment_nepust', 'fio', 'fio_inic', 'fio_poln',
                          'dolzh', 'pochta', 'fio_i_dolzh', 'teh_slovo',
                          'fio_bez_tel', 'tolko_zakryt')}
    komp_fio = set()
    komp_vse = set()
    primery = []
    dlin = []

    for r in otsech:
        c = (r.get('comment') or '').replace('&nbsp;', ' ')
        komp_vse.add(r.get('company_id') or r.get('company'))
        if not c.strip():
            continue
        sch['comment_nepust'] += 1
        dlin.append(len(c))
        f_in = FIO_INIC.findall(c) + INIC_FIO.findall(c)
        f_pl = [m for m in FIO_POLN.findall(c) if not MUSOR.match(m)]
        fio = f_in + f_pl
        d = DOLZH.search(c)
        p = POCHTA.findall(c)
        if f_in:
            sch['fio_inic'] += 1
        if f_pl:
            sch['fio_poln'] += 1
        if fio:
            sch['fio'] += 1
            komp_fio.add(r.get('company_id') or r.get('company'))
        if d:
            sch['dolzh'] += 1
        if p:
            sch['pochta'] += 1
        if fio and d:
            sch['fio_i_dolzh'] += 1
        if TEH.search(c):
            sch['teh_slovo'] += 1
        if fio and d and len(primery) < 12:
            primery.append((r['tender_id'], r['company'], c[:400], fio[:4], d.group(0)))

    print(f'комментарий непуст:            {sch["comment_nepust"]:5d} / {n}'
          f'  ({100 * sch["comment_nepust"] / n:.1f}%)')
    print(f'  похоже на ФИО (любой вид):   {sch["fio"]:5d} / {n}'
          f'  ({100 * sch["fio"] / n:.1f}%)')
    print(f'    из них «Фамилия И.О.»:     {sch["fio_inic"]:5d}')
    print(f'    из них два-три слова:      {sch["fio_poln"]:5d}')
    print(f'  слово о должности:           {sch["dolzh"]:5d} / {n}'
          f'  ({100 * sch["dolzh"] / n:.1f}%)')
    print(f'  ФИО И должность вместе:      {sch["fio_i_dolzh"]:5d} / {n}'
          f'  ({100 * sch["fio_i_dolzh"] / n:.1f}%)')
    print(f'  почта:                       {sch["pochta"]:5d} / {n}'
          f'  ({100 * sch["pochta"] / n:.1f}%)')
    print(f'  техническое слово (мой набор): {sch["teh_slovo"]:5d} / {n}'
          f'  ({100 * sch["teh_slovo"] / n:.1f}%)  <-- расхождение с est_teh')
    print()
    print(f'компаний в отсечённых: {len(komp_vse)}, из них с ФИО в комментарии: {len(komp_fio)}')
    if dlin:
        dlin.sort()
        print(f'длина непустого комментария: медиана {dlin[len(dlin) // 2]}, '
              f'макс {dlin[-1]}, мин {dlin[0]}')
    print()
    print('=== ПРИМЕРЫ отсечённых карточек с ФИО и должностью ===')
    for tid, comp, c, fio, d in primery:
        print(f'\n[{tid}] {comp}\n  ФИО-кандидаты: {fio}\n  должность-слово: {d}\n  {c}')


if __name__ == '__main__':
    main()
