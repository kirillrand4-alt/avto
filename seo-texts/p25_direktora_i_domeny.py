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
VYH_SAYT = r'C:\sender\_ops\3s_p25_sayty.csv'
OTCH = re.compile(r'(?:ович|евич|ьевич|инич|овна|евна|ьевна|ична|инична)\b', re.I)
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
    direktora, imena = [], {}
    for inn, predpr, direktor in b.execute(
            'select inn, coalesce(predpriyatie,""), coalesce(direktor,"") from company'):
        imena[inn] = predpr
        d = direktor.strip()
        if not d:
            sch['директора нет'] += 1
            continue
        # В поле может стоять «Генеральный директор Иванов Иван Иванович» или просто ФИО.
        slova = [s for s in re.split(r'[\s,]+', d) if s]
        fio = [s for s in slova if re.match(r'^[А-ЯЁ][а-яё-]+$', s) or s.isupper()]
        # ФИО — три слова подряд, среднее с отчественным окончанием.
        polnoe = ''
        for i in range(len(fio) - 2):
            trio = fio[i:i + 3]
            if OTCH.search(trio[2]) or OTCH.search(trio[1]):
                polnoe = ' '.join(t.title() if t.isupper() else t for t in trio)
                break
        if not polnoe:
            sch['директор записан не полным ФИО'] += 1
            continue
        sch['ДИРЕКТОР С ПОЛНЫМ ФИО'] += 1
        direktora.append({'inn': inn, 'predpriyatie': predpr, 'fio': polnoe,
                          'dolzhnost': 'руководитель (ЕГРЮЛ), не технический круг',
                          'otkuda': 'company.direktor из p25.db'})

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
            (VYH_SAYT, sayty, ['inn', 'predpriyatie', 'sayt', 'otkuda', 'ssylok'])):
        with open(put, 'w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, delimiter=';', fieldnames=polya)
            w.writeheader()
            w.writerows(dann)
    for z in direktora[:4] + sayty[:4]:
        print('REC ' + json.dumps(z, ensure_ascii=False))
    print('ИТОГ ' + json.dumps({'директоров': len(direktora), 'файл_директоров': VYH_DIR,
                                'сайтов': len(sayty), 'файл_сайтов': VYH_SAYT,
                                'счёт': dict(sch.most_common())}, ensure_ascii=False))


if __name__ == '__main__':
    main()
