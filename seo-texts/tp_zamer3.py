# -*- coding: utf-8 -*-
"""Замер-3: пересечение признаков в отсечённых карточках + контроль живости фильтра.

Выводит:
  1. таблицу пересечений «сильное ФИО» × «номер, потерянный регуляркой harvest»;
  2. контроль живости (правило 1): контрольная бессмыслица должна дать 0,
     осмысленное слово — не 0, счётчик разобран;
  3. файл-кандидат `tp-otsech-kandidaty.csv` для разбора провайдером.
"""
import csv
import os
import re

BAZA = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BAZA, 'engineers-lens', 'centro', 'tenderpro')
KART = os.path.join(OUT, 'tp-kartochki.csv')
KAND = os.path.join(OUT, 'tp-otsech-kandidaty.csv')

TEL_HARVEST = re.compile(r'(?:\+7|\b8)[\s(\-]*\d{3,5}[\s)\-]*\d{2,3}[\s\-]*\d{2}[\s\-]*\d{2}\b')
TEL_SHIROKO = re.compile(
    r'(?:\+7|\b8|\b7)[\s()\-.]*\d{3,5}[\s()\-.]*\d{2,4}[\s\-.]*\d{2,4}(?:[\s\-.]*\d{2})?'
    r'|(?:тел|моб|факс|т\.)[^0-9]{0,12}(\d[\d\s()\-.]{8,18}\d)', re.I)
OTCH = re.compile(r'\b[А-ЯЁ][а-яё]+(?:ович|евич|ьевич|овна|евна|ична|ьевна|инична)\b')
FIO_INIC = re.compile(r'([А-ЯЁ][а-яё]{2,})\s+([А-ЯЁ])\.\s?([А-ЯЁ])\.')
INIC_FIO = re.compile(r'([А-ЯЁ])\.\s?([А-ЯЁ])\.\s*([А-ЯЁ][а-яё]{2,})')
POCHTA = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
MUSOR = re.compile(r'^(?:Российск|Гражданск|Федеральн|Обществ|Закрыт|Открыт|Публичн|Акционерн|'
                   r'Ограничен|Единый|Электронн|Торгов|Запрос|Коммерческ|Техническ|Приложен|'
                   r'Договор|Заказчик|Организатор|Участник|Победител|Комисси|Республик|Област|'
                   r'Настоящ|Данн|Указан|Извещен|Документ|Протокол|Поставк|Услуг|Работ|Товар|'
                   r'Налогов|Деловые|Крайнего|Город|Правил|Кодекс|Отдел|Служб|Управлен|Центр|'
                   r'Завод|Комбинат|Группа|Компан|Фирм|Дирекц|Филиал|Стоимост|Условия|Требован|'
                   r'Гарант|Оплат|Срок|Цена|Внимание|Просьб|Прош|Все|Любые)', re.I)
# слово, по которому провайдеру стоит смотреть карточку: обращение к человеку
OBRASH = re.compile(r'обращат|обращен|контактн\w*\s+лиц|куратор|ответственн\w*\s+лиц|'
                    r'вопрос\w*\s+(?:по|направля|адресова)|консультац|исполнител', re.I)


def silnoe_fio(c):
    r = [m.group(0) for m in OTCH.finditer(c)]
    r += [m.group(0) for m in FIO_INIC.finditer(c) if not MUSOR.match(m.group(1))]
    r += [m.group(0) for m in INIC_FIO.finditer(c) if not MUSOR.match(m.group(3))]
    return list(dict.fromkeys(r))


def main():
    rows = list(csv.DictReader(open(KART, encoding='utf-8-sig'), delimiter=';'))
    ots = [r for r in rows
           if not ((r.get('telefony_razmetka') or '') + (r.get('telefony_tekst') or ''))
           and not r.get('est_teh')]
    n = len(ots)

    # --- контроль живости фильтра (правило 1) ---
    besmyslica = sum(1 for r in ots if 'кастрюлякастрюля' in (r.get('comment') or ''))
    osmysl = sum(1 for r in ots if 'оплат' in (r.get('comment') or '').lower())
    est_teh_v_ots = sum(1 for r in ots if r.get('est_teh'))
    tel_v_ots = sum(1 for r in ots
                    if (r.get('telefony_razmetka') or '') + (r.get('telefony_tekst') or ''))
    print('=== КОНТРОЛЬ ЖИВОСТИ (правило 1) ===')
    print(f'всего строк прочитано из CSV:                     {len(rows)}')
    print(f'отсечённых:                                       {n}')
    print(f'контрольная бессмыслица «кастрюлякастрюля»:        {besmyslica}  (ожидание 0)')
    print(f'осмысленное слово «оплат» в отсечённых:            {osmysl}  (ожидание не 0)')
    print(f'est_teh непуст среди отсечённых:                   {est_teh_v_ots}  (ожидание 0 — фильтр применён)')
    print(f'телефон harvest непуст среди отсечённых:           {tel_v_ots}  (ожидание 0 — фильтр применён)')

    a = b = ab = ni = 0
    kand = []
    for r in ots:
        c = (r.get('comment') or '').replace('&nbsp;', ' ').replace('&ndash;', '-')
        c = re.sub(r'^\s*Комментарий:\s*', '', c).strip()
        fio = silnoe_fio(c)
        tel_lost = bool(TEL_SHIROKO.search(c)) and not TEL_HARVEST.search(c)
        if fio and tel_lost:
            ab += 1
        elif fio:
            a += 1
        elif tel_lost:
            b += 1
        else:
            ni += 1
        if fio or tel_lost or (POCHTA.search(c) and OBRASH.search(c)):
            kand.append(dict(r, comment=c, fio_kand=' | '.join(fio[:5]),
                             tel_poteryan='1' if tel_lost else ''))

    print('\n=== ПЕРЕСЕЧЕНИЕ ПРИЗНАКОВ (знаменатель %d отсечённых карточек) ===' % n)
    print(f'сильное ФИО и потерянный номер вместе: {ab:5d}')
    print(f'только сильное ФИО, номера нет:        {a:5d}')
    print(f'только потерянный номер, ФИО нет:      {b:5d}')
    print(f'ни того, ни другого:                   {ni:5d}')
    print(f'сумма-проверка: {ab + a + b + ni} == {n}')

    komp = {r['company_id'] for r in kand}
    print(f'\nкандидатов к разбору провайдером: {len(kand)} карточек, {len(komp)} компаний')

    cols = ['tender_id', 'company_id', 'company', 'predmet', 'sozdan', 'pochty',
            'fio_kand', 'tel_poteryan', 'comment']
    with open(KAND, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter=';', extrasaction='ignore')
        w.writeheader()
        for r in kand:
            w.writerow(r)
    print(f'записано → {KAND}')


if __name__ == '__main__':
    main()
