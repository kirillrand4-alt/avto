# -*- coding: utf-8 -*-
"""Что уже лежит в p25.db и не использовано: 474 директора и домены из ссылок контактов.

ЗАМЕР, С КОТОРОГО ЭТО НАЧАЛОСЬ. Перепись колонок `company` (76 колонок, 491 предприятие):
непустых всего 21. Пусты насквозь `sayt`, `pochta`, `telefony_iz_bazy`, `telefony_checko` —
то есть ни сайта, ни телефона предприятия в базе нет вовсе. А `direktor` заполнен у **474 из
491**, и до сих пор не использован никем.

ЗАЧЕМ ДИРЕКТОР, ЕСЛИ МЕРА — ТЕХНИЧЕСКИЙ ЛПР. Затем, что это 474 готовых входа обратного хода
с бесспорной привязкой к предприятию: ФИО директора приходит из ЕГРЮЛ, а не из выдачи, то
есть пара «человек ↔ ИНН» доказана до всякого поиска. Роль пишется честно — «руководитель, не
технический круг», — и в главную меру такой человек не идёт. Но: страница, на которой
находится директор, почти всегда сайт самого предприятия, а это ровно то, чего мне не хватает
для строгой приёмки; и через приёмную директора продавец доходит до главного инженера, когда
прямого номера нет.

ВТОРОЕ ЗДЕСЬ — ДОМЕНЫ ИЗ УЖЕ ДОБЫТЫХ ССЫЛОК. В `contact` 2 568 записей, и `source_url`
заполнен у ВСЕХ. Большинство ведёт на площадки, но часть — на сайты самих предприятий, и эти
домены достаются даром, без единого запроса. Отбор строгий: домен засчитывается сайтом
предприятия, только если `chuzhaya_stranica` подтверждает страницу по имени предприятия в
адресе, — иначе в колонку `sayt` уедет etpgpb.ru и завтра «подтверждено сайтом предприятия»
будет означать «подтверждено площадкой».

Пишет два файла и ничего не меняет в базе.
"""
import collections
import csv
import json
import re
import sqlite3
import sys

sys.path.insert(0, r'C:\sender\_ops')

BAZA = 'file:C:/seostat/data/p25.db?mode=ro'
VYH_DIR = r'C:\sender\_ops\3s_p25_direktora.csv'
VYH_UK = r'C:\sender\_ops\3s_p25_upravlyayushchie.csv'
VYH_SAYT = r'C:\sender\_ops\3s_p25_sayty.csv'
OTCH = re.compile(r'(?:ович|евич|ьевич|инич|овна|евна|ьевна|ична|инична)\b', re.I)
# В поле `direktor` вместо человека может стоять ЮРЛИЦО: по ЕГРЮЛ исполнительным органом
# бывает управляющая компания. Это не брак записи и не «директора нет» — это ИМЯ ХОЛДИНГА,
# и оно ценно вдвойне: страница на сайте холдинга по ТЗ считается подтверждением, а
# технический ЛПР у таких предприятий часто сидит именно в управляющей компании.
YURLICO = re.compile(r'ОБЩЕСТВО С ОГРАНИЧЕННОЙ|АКЦИОНЕРНОЕ ОБЩЕСТВО|УПРАВЛЯЮЩАЯ КОМПАНИЯ|'
                     r'\bООО\b|\bАО\b|\bПАО\b|\bЗАО\b|\bОАО\b|КОМПАНИЯ|ОБЪЕДИНЕНИЕ|'
                     r'КОМБИНАТ|ГРУППА|ХОЛДИНГ|МЕНЕДЖМЕНТ|["«»]', re.I)
DOLZHNOST_V_POLE = re.compile(
    r'\b(ГЕНЕРАЛЬНЫЙ ДИРЕКТОР|ИСПОЛНИТЕЛЬНЫЙ ДИРЕКТОР|УПРАВЛЯЮЩИЙ|ДИРЕКТОР|ПРЕЗИДЕНТ|'
    r'РУКОВОДИТЕЛЬ|ПРЕДСЕДАТЕЛЬ ПРАВЛЕНИЯ|КОНКУРСНЫЙ УПРАВЛЯЮЩИЙ)\b', re.I)
NE_SAYT = re.compile(
    r'zakupki\.gov|roseltorg|rts-tender|etp-?gpb|etpgpb|tektorg|tender\.pro|b2b-center|'
    r'sberbank-ast|fabrikant|otc\.ru|gazneftetorg|estp|torgi\.gov|rusprofile|list-org|'
    r'checko|sbis|kartoteka|audit-it|zachestnyibiznes|datanewton|kontur|b2book|rbc\.|'
    r'inndex|companies|hh\.ru|superjob|vk\.com|ok\.ru|t\.me|youtube|dzen|wikipedia', re.I)


def yadro(url):
    v = re.sub(r'^\w+://', '', (url or '').strip().lower()).split('/')[0].split('?')[0]
    ch = [c for c in v.split('.') if c and c != 'www']
    return '.'.join(ch[-2:]) if len(ch) >= 2 else (ch[0] if ch else '')


def translit(imya):
    osnova = re.sub(r'[^а-яёa-z0-9]', '',
                    re.sub(r'\b(ООО|ОАО|ЗАО|ПАО|АО|НАО|ФГУП|ГУП|МУП|ФГБУ)\b', '',
                           imya, flags=re.I).lower())
    tr = str.maketrans({'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
                        'ж': 'z', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
                        'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
                        'ф': 'f', 'х': 'h', 'ц': 'c', 'ч': 'c', 'ш': 's', 'щ': 's', 'ъ': '',
                        'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'u', 'я': 'a'})
    return osnova.translate(tr)


def main():
    b = sqlite3.connect(BAZA, uri=True)
    sch = collections.Counter()
    direktora, upravlyayushchie, imena = [], [], {}
    for inn, predpr, direktor in b.execute(
            'select inn, coalesce(predpriyatie,""), coalesce(direktor,"") from company'):
        imena[inn] = predpr
        d = direktor.strip()
        if not d:
            sch['директора нет'] += 1
            continue
        if YURLICO.search(d):
            # Исполнительный орган — управляющая компания. Человека тут нет и не будет,
            # зато есть имя холдинга: и путь к техническому ЛПР, и законный источник
            # подтверждения по правилу «страница про предприятие на сайте холдинга».
            sch['УПРАВЛЯЮЩАЯ КОМПАНИЯ вместо человека'] += 1
            upravlyayushchie.append({'inn': inn, 'predpriyatie': predpr,
                                     'upravlyayushchaya': d,
                                     'otkuda': 'company.direktor из p25.db — юрлицо'})
            continue
        # В поле может стоять «Иванов Иван Иванович ГЕНЕРАЛЬНЫЙ ДИРЕКТОР» или просто ФИО.
        # Должность из строки убираем ДО разбора имени: иначе слово «ДИРЕКТОР» встанет
        # третьим словом и уедет в базу как отчество.
        chistoe = DOLZHNOST_V_POLE.sub(' ', d)
        slova = [s for s in re.split(r'[\s,]+', chistoe) if s and re.match(r'^[А-ЯЁ]', s)]
        polnoe = ''
        for i in range(max(0, len(slova) - 2)):
            trio = slova[i:i + 3]
            if len(trio) == 3 and (OTCH.search(trio[2]) or OTCH.search(trio[1])):
                polnoe = ' '.join(t.title() if t.isupper() else t for t in trio)
                break
        vid = 'полное ФИО с отчеством'
        if not polnoe and 2 <= len(slova) <= 3:
            # ОТЧЕСТВО — ПРАВИЛО ПОИСКОВОГО КАНАЛА, А НЕ РЕЕСТРА, и переносить его сюда
            # было ошибкой. Требование отчества существует затем, чтобы «Иванов И.И.» в
            # выдаче не притянул однофамильцев с других заводов. Здесь имя приходит из
            # ЕГРЮЛ вместе с ИНН — привязка человека к предприятию доказана ДО всякого
            # поиска, и различать однофамильцев не нужно. Отбрасывая имена без отчества,
            # я молча теряла настоящих руководителей: «Окйар Тарик», «Вахун Михал»,
            # «Гёнджу Уфук» — иностранные имена, у которых отчества нет в природе.
            polnoe = ' '.join(t.title() if t.isupper() else t for t in slova)
            vid = 'имя без отчества (иностранное или сокращённая запись ЕГРЮЛ)'
        if not polnoe:
            sch['имя не разобрано: ' + (d[:40] or 'пусто')] += 1
            continue
        sch['ДИРЕКТОР-ЧЕЛОВЕК: ' + vid] += 1
        direktora.append({'inn': inn, 'predpriyatie': predpr, 'fio': polnoe,
                          'dolzhnost': 'руководитель (ЕГРЮЛ), не технический круг',
                          'otkuda': 'company.direktor из p25.db — ' + vid})

    # Домены из ссылок уже добытых контактов.
    kand = collections.defaultdict(collections.Counter)
    for inn, url in b.execute(
            'select inn, coalesce(source_url,"") from contact where coalesce(source_url,"")<>""'):
        y = yadro(url)
        if not y or NE_SAYT.search(url):
            continue
        kand[inn][y] += 1
    sayty = []
    for inn, sch_dom in kand.items():
        lat = translit(imena.get(inn, ''))
        for dom, n in sch_dom.most_common():
            golo = re.sub(r'[^a-z0-9]', '', dom)
            # Домен признаётся своим, только если имя предприятия узнаётся в нём.
            if len(lat) >= 4 and (lat[:8] in golo or golo.split('.')[0][:8] in lat):
                sayty.append({'inn': inn, 'predpriyatie': imena.get(inn, ''), 'sayt': dom,
                              'otkuda': 'домен ссылки уже добытого контакта, имя предприятия '
                                        'узнаётся в адресе', 'ssylok': n})
                sch['САЙТ ИЗ ССЫЛОК КОНТАКТОВ'] += 1
                break
        else:
            sch['домены у контактов есть, но имя предприятия в них не узнаётся'] += 1

    for put, dann, polya in (
            (VYH_DIR, direktora, ['inn', 'predpriyatie', 'fio', 'dolzhnost', 'otkuda']),
            (VYH_UK, upravlyayushchie, ['inn', 'predpriyatie', 'upravlyayushchaya', 'otkuda']),
            (VYH_SAYT, sayty, ['inn', 'predpriyatie', 'sayt', 'otkuda', 'ssylok'])):
        with open(put, 'w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, delimiter=';', fieldnames=polya)
            w.writeheader()
            w.writerows(dann)
    for z in direktora[:4] + sayty[:4]:
        print('REC ' + json.dumps(z, ensure_ascii=False))
    print('ИТОГ ' + json.dumps({'директоров': len(direktora), 'файл_директоров': VYH_DIR,
                                'управляющих_компаний': len(upravlyayushchie),
                                'файл_управляющих': VYH_UK,
                                'сайтов': len(sayty), 'файл_сайтов': VYH_SAYT,
                                'счёт': dict(sch.most_common())}, ensure_ascii=False))


if __name__ == '__main__':
    main()
