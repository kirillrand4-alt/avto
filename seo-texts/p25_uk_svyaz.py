# -*- coding: utf-8 -*-
"""62 управляющие компании: превратить «директора нет» в путь, а не в пустую клетку.

ЧТО ЭТО ЗА 62. В `company.direktor` у них стоит не человек, а ЮРЛИЦО: по ЕГРЮЛ исполнительным
органом бывает управляющая компания — «ООО УК "ПОЛЮС"», «АО "УК "УРАЛЬСКИЙ ЦЕМЕНТ"». Мой
первый разбор считал такие записи браком («директор записан не полным ФИО») и молча их ронял.
Это не брак: это ИМЯ ХОЛДИНГА, и оно ценно трижды.

  1. ПОДТВЕРЖДЕНИЕ. По ТЗ страница про предприятие на сайте владеющего холдинга —
     первоисточник. Заслон умеет это правило, но сравнивает адрес страницы только с именем
     САМОГО предприятия. Для «АККЕРМАНН ЦЕМЕНТ» страница на сайте «Уральского цемента» не
     подтвердится, хотя по существу должна. Имя УК даёт заслону второе имя для сравнения.
  2. ТЕХНИЧЕСКИЙ ЛПР. У предприятий под управлением главный инженер и главный механик часто
     сидят в самой УК, а не на площадке. Искать их по имени площадки бесполезно.
  3. СВЯЗЬ ВНУТРИ СПИСКА. Часть УК — сами покупатели из наших же 491. Тогда люди холдинга уже
     добыты, и их надо только связать, а не искать заново.

ЗДЕСЬ НИ ОДНОГО ЗАПРОСА В ПОИСК: только сшивка по именам внутри базы. Сшивка по ЯДРУ имени,
как в `yadro_imeni`: «УПРАВЛЯЮЩАЯ КОМПАНИЯ ПОЛЮС» и «ПОЛЮС» — одно, «БСК» и «БЭСК» — разное.
"""
import collections
import csv
import json
import os
import re
import sqlite3

BAZA = 'file:C:/seostat/data/p25.db?mode=ro'
VYHOD = r'C:\sender\_ops\3s_p25_uk_svyaz.csv'
FORMY = re.compile(
    r'\b(ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ|'
    r'(?:ПУБЛИЧНОЕ |ОТКРЫТОЕ |ЗАКРЫТОЕ |НЕПУБЛИЧНОЕ |МЕЖДУНАРОДНАЯ КОМПАНИЯ )?'
    r'АКЦИОНЕРНОЕ ОБЩЕСТВО|УПРАВЛЯЮЩАЯ КОМПАНИЯ|ХОЛДИНГОВАЯ КОМПАНИЯ|ГРУППА|'
    r'ООО|ОАО|ЗАО|ПАО|АО|НАО|УК)\b', re.I)
YURLICO = re.compile(r'ОБЩЕСТВО С ОГРАНИЧЕННОЙ|АКЦИОНЕРНОЕ ОБЩЕСТВО|УПРАВЛЯЮЩАЯ КОМПАНИЯ|'
                     r'\bООО\b|\bАО\b|\bПАО\b|\bЗАО\b|\bОАО\b|КОМПАНИЯ|ОБЪЕДИНЕНИЕ|'
                     r'КОМБИНАТ|ГРУППА|ХОЛДИНГ|МЕНЕДЖМЕНТ|["«»]', re.I)


def yadro(imya):
    """Ядро названия: формы собственности и кавычки прочь, остаётся отличающее слово."""
    v = FORMY.sub(' ', (imya or '').upper())
    v = re.sub(r'[^А-ЯЁA-Z0-9]+', ' ', v)
    return ' '.join(v.split())


def main():
    b = sqlite3.connect(BAZA, uri=True)
    vse = [(inn, predpr, (direktor or '').strip()) for inn, predpr, direktor in b.execute(
        'select inn, coalesce(predpriyatie,""), coalesce(direktor,"") from company')]
    po_yadru = collections.defaultdict(list)
    for inn, predpr, _ in vse:
        y = yadro(predpr)
        if len(y) >= 4:
            po_yadru[y].append((inn, predpr))

    sch = collections.Counter()
    ryady = []
    for inn, predpr, direktor in vse:
        if not direktor or not YURLICO.search(direktor):
            continue
        sch['управляющих компаний'] += 1
        yu = yadro(direktor)
        # Совпадение по ядру — полное или вхождение: «УПРАВЛЯЮЩАЯ КОМПАНИЯ ПОЛЮС» → «ПОЛЮС».
        sovpalo = []
        for y, spisok in po_yadru.items():
            if y == yu or (len(y) >= 4 and (y in yu or yu in y)):
                for i2, p2 in spisok:
                    if i2 != inn:
                        sovpalo.append((i2, p2))
        if sovpalo:
            sch['УК ЕСТЬ В НАШИХ ЖЕ 491 — люди холдинга уже добыты'] += 1
        else:
            sch['УК вне списка — имя годится заслону и поиску'] += 1
        ryady.append({
            'inn': inn, 'predpriyatie': predpr, 'upravlyayushchaya': direktor,
            'yadro_uk': yu,
            'uk_v_spiske_inn': ' | '.join(i for i, _ in sovpalo),
            'uk_v_spiske_imya': ' | '.join(p for _, p in sovpalo),
            'zachem': ('люди холдинга уже в базе — связать, а не искать' if sovpalo
                       else 'второе имя для заслона и точка поиска технического ЛПР'),
        })

    with open(VYHOD, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, delimiter=';', fieldnames=[
            'inn', 'predpriyatie', 'upravlyayushchaya', 'yadro_uk', 'uk_v_spiske_inn',
            'uk_v_spiske_imya', 'zachem'])
        w.writeheader()
        w.writerows(ryady)
    for z in ryady[:10]:
        print('REC ' + json.dumps({k: z[k] for k in
                                   ('inn', 'predpriyatie', 'upravlyayushchaya',
                                    'uk_v_spiske_imya')}, ensure_ascii=False))
    print('ИТОГ ' + json.dumps({'файл': VYHOD, 'строк': len(ryady),
                                'счёт': dict(sch.most_common())}, ensure_ascii=False))


if __name__ == '__main__':
    main()
