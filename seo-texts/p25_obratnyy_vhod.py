# -*- coding: utf-8 -*-
"""Собрать вход обратного хода P25 из чужих и своих списков имён.

ЗАЧЕМ. Обратный ход ищет номер по паре «ФИО + имя предприятия» — без второй половины запрос
находит однофамильцев по всей стране. А в обоих списках имён предприятия НЕТ:

  * `P25-LYUDI-2S-001.csv` — 251 человек 2-й сессии с карточек ЭТП ГПБ, 207 без личного
    мобильного. Колонки inn/chelovek/dolzhnost, названия предприятия нет ни в одной.
  * `P25-LYUDI-3S-ne-podtverzhdeno-003.csv` — 258 моих кандидатов: имя и должность есть,
    первоисточника нет. Им обратный ход нужен вдвойне: страница, на которой лежит личный
    номер человека, сама по себе чаще всего и есть первоисточник (сайт предприятия,
    карточка закупки), то есть один прогон закрывает обе дыры сразу.

Имя предприятия берётся из `p25.db` по ИНН. ИМЯ КОЛОНКИ НЕ УГАДЫВАЕТСЯ: базу собирала 1-я
сессия, и мой же зафиксированный промах — придумать `name`/`company_name`, получить честный
ноль и прочитать его как «ошибок нет». Поэтому здесь сперва `PRAGMA table_info`, и найденное
имя колонки печатается в отчёте: если подходящей колонки нет, это будет ВИДНО, а не сойдёт
за пустой результат.

Кого пропускаем: у кого личный мобильный уже есть — обратный ход им ничего не добавит.
Пропущенные считаются и называются, а не исчезают.
"""
import collections
import csv
import json
import os
import re
import sqlite3
import sys

VHODY = [r'C:\sender\_ops\3s_p25_vhod_2s.csv', r'C:\sender\_ops\3s_p25_vhod_3s.csv',
         # ТРЕТИЙ ВХОД — ДИРЕКТОРА ИЗ ЕГРЮЛ. 412 человек, чью привязку к предприятию не надо
         # доказывать: она пришла вместе с ИНН из реестра, а не из выдачи. В главную меру
         # они не идут (роль записана «руководитель (ЕГРЮЛ), не технический круг»), но
         # страница, на которой находится директор, почти всегда сайт самого предприятия —
         # то есть попутно добывается ровно то, чего не хватает строгой приёмке.
         r'C:\sender\_ops\3s_p25_direktora.csv',
         # ЧЕТВЁРТЫЙ ВХОД — ЛЮДИ С КАРТОЧЕК ПЛОЩАДКИ. 390 имён с полным отчеством, у
         # которых личного мобильного нет нигде в разборе карточек, 69 из них на наших
         # покупателях. Их привязку к предприятию тоже не надо доказывать: человек назван
         # в закупке самого предприятия, словами заказчика.
         #
         # Появился этот вход оттого, что канал встал: 1 062 полных ФИО, спрошено 1 070,
         # к обходу ноль. Канал был жив, ему было нечего есть — при том что новый
         # источник имён я добыла часом раньше и своему же каналу не предложила. Это
         # третий за смену случай, когда два моих потока лежат рядом и не пересекаются.
         # Правило: КАЖДЫЙ НОВЫЙ ИСТОЧНИК ИМЁН ПРЕДЛАГАЕТСЯ КАЖДОМУ КАНАЛУ, КОТОРЫЙ ЕСТ
         # ИМЕНА, иначе добыча оседает в файле, где её никто не спрашивает.
         r'C:\sender\_ops\3s_p25_vhod_iz_kartochek.csv']
BAZA = r'C:\seostat\data\p25.db'
VYHOD = r'C:\sender\_ops\3s_p25_obratnyy_vhod.csv'
IMENA_KOLONOK = ('predpriyatie', 'naimenovanie', 'name', 'company_name', 'kratkoe_naimenovanie',
                 'polnoe_naimenovanie', 'nazvanie', 'org', 'title')
OTCH = re.compile(r'(?:ович|евич|ьевич|инич|овна|евна|ьевна|ична|инична)\b')


def lichnyy(nomer):
    """Личный мобильный: 11 цифр, начинается на 79. Добавочные и городские сюда не попадают."""
    c = re.sub(r'\D', '', str(nomer or ''))
    if len(c) == 11 and c[0] in '78':
        c = '7' + c[1:]
    return len(c) == 11 and c.startswith('79')


def imena_predpriyatiy():
    """{инн: имя} из p25.db. Возвращает также объяснение, откуда взято."""
    if not os.path.exists(BAZA):
        return {}, f'базы {BAZA} нет — имена предприятий взять неоткуда'
    b = sqlite3.connect('file:' + BAZA + '?mode=ro', uri=True)
    try:
        tabl = [r[0] for r in b.execute(
            "select name from sqlite_master where type='table'")]
        if 'company' not in tabl:
            return {}, 'в p25.db нет таблицы company; таблицы: ' + ', '.join(tabl[:20])
        kol = [r[1] for r in b.execute('pragma table_info(company)')]
        imya_kol = next((k for k in IMENA_KOLONOK if k in kol), None)
        if not imya_kol:
            return {}, ('в company нет колонки с названием; её колонки: ' + ', '.join(kol))
        inn_kol = next((k for k in ('inn', 'INN', 'inn_kod') if k in kol), None)
        if not inn_kol:
            return {}, 'в company нет колонки inn; её колонки: ' + ', '.join(kol)
        d = {}
        for inn, imya in b.execute(
                f'select {inn_kol}, coalesce({imya_kol}, "") from company'):
            if inn and imya:
                d[str(inn).strip()] = str(imya).strip()
        return d, f'company.{imya_kol} по company.{inn_kol}, записей {len(d)}'
    finally:
        b.close()


def main():
    imena, otkuda = imena_predpriyatiy()
    sch = collections.Counter()
    lyudi = {}
    for put in VHODY:
        if not os.path.exists(put):
            sch['ВХОДА НЕТ: ' + os.path.basename(put)] += 1
            continue
        csv.field_size_limit(10 ** 7)
        for r in csv.DictReader(open(put, encoding='utf-8-sig'), delimiter=';'):
            sch['строк прочитано'] += 1
            fio = (r.get('chelovek') or r.get('fio') or '').strip()
            inn = (r.get('inn') or '').strip()
            iz_reestra = (r.get('otkuda') or '').startswith('company.direktor')
            # ОТЧЕСТВО ТРЕБУЕТСЯ ОТ ВЫДАЧИ, А НЕ ОТ РЕЕСТРА. «Иванов И.И.» в кавычках находит
            # однофамильцев по всей стране — вот зачем правило написано. У директора из
            # ЕГРЮЛ пара «человек ↔ ИНН» доказана до всякого поиска, различать однофамильцев
            # незачем, и отчества у «Окйар Тарик» нет в природе.
            if not (inn and fio):
                sch['пропущено: нет ИНН или имени'] += 1
                continue
            if iz_reestra:
                if len(fio.split()) < 2:
                    sch['пропущено: в реестре одно слово вместо имени'] += 1
                    continue
            elif len(fio.split()) < 3 or not OTCH.search(fio):
                sch['пропущено: не полное ФИО'] += 1
                continue
            if lichnyy(r.get('telefon')):
                sch['пропущено: личный мобильный уже есть'] += 1
                continue
            imya = imena.get(inn, '')
            if not imya:
                sch['пропущено: имени предприятия по ИНН не нашлось'] += 1
                continue
            k = (inn, fio)
            if k in lyudi:
                sch['дубль имени (тот же человек из двух списков)'] += 1
                continue
            lyudi[k] = {'inn': inn, 'predpriyatie': imya, 'fio': fio,
                        'dolzhnost': (r.get('dolzhnost') or '').strip(),
                        'otkuda': os.path.basename(put)}
            sch['В ОБХОД'] += 1

    with open(VYHOD, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['inn', 'predpriyatie', 'fio', 'dolzhnost', 'otkuda'],
                           delimiter=';')
        w.writeheader()
        w.writerows(lyudi.values())

    for z in list(lyudi.values())[:8]:
        print('REC ' + json.dumps(z, ensure_ascii=False))
    print('ИТОГ ' + json.dumps({'имена_предприятий': otkuda, 'файл': VYHOD,
                                'счёт': dict(sch.most_common())}, ensure_ascii=False))


if __name__ == '__main__':
    sys.exit(main())
