# -*- coding: utf-8 -*-
"""Пересчёт главной меры по 365 видимым: у кого имя есть, а телефона нет.

После приговора по словарю видимых стало 365 (было 973+). Прежний счёт целей
«телефон к известному ФИО» (272 предприятия) снят со старого множества — часть
целей ушла в скрытые, тратить каналы на них нельзя. Считаем заново и кладём
очередь на дроп, отсортированную по приговору (покупает > есть > планирует) и
числу известных имён.
"""
import csv
import io
import json
import os
import re
import sqlite3
import urllib.request
from collections import Counter

ЦБ = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
ПР = os.getenv('CENTRO_SALES_DB') or r'C:\seostat\data\centro_sales.db'
ВЫХОД = 'CELI-TELEFON-K-FIO-365.csv'
_ТЕХ = re.compile(r'инженер|энергетик|механик|технолог|производств|конструктор|'
                  r'техничес|метролог|оборудован|главн\w*\s+свар', re.I)
ВЕС = {'покупает': 0, 'есть': 1, 'планирует': 2, 'планировал': 3}


def main():
    пр = sqlite3.connect(f'file:{ПР}?mode=ro', uri=True, timeout=20)
    скрыты = {str(r[0]) for r in пр.execute(
        "SELECT inn FROM hidden_item WHERE kind='company'")}
    приговор = {str(r[0]): (r[1] or '') for r in пр.execute(
        'SELECT inn, verdikt FROM sud_verdikt')}
    пр.close()

    цб = sqlite3.connect(f'file:{ЦБ}?mode=ro', uri=True, timeout=20)
    кол = [c[1] for c in цб.execute('PRAGMA table_info("company")')]
    имя_к = next((k for k in ('predpriyatie', 'name', 'name_full')
                  if k in кол), 'inn')
    компании = {str(r[0]): (r[1] or '') for r in цб.execute(
        f'SELECT inn, "{имя_к}" FROM company')}
    видимые = {и for и in компании if и not in скрыты}

    # person: колонки person/position/role/phone/is_tech (схема снята с базы).
    # Телефон человека может лежать и в contact (kind=phone, person=ФИО) —
    # считаем человека «с телефоном», если номер есть хоть в одном месте.
    тел_из_contact = set()
    for r in цб.execute(
            "SELECT inn, COALESCE(person,'') FROM contact "
            "WHERE kind='phone' AND COALESCE(person,'')<>'' "
            "AND COALESCE(value,'')<>''"):
        тел_из_contact.add((str(r[0]), str(r[1]).strip().lower()))
    люди = {}
    for r in цб.execute(
            "SELECT inn, COALESCE(person,''), COALESCE(position,''), "
            "COALESCE(role,''), COALESCE(phone,''), COALESCE(is_tech,0) "
            "FROM person WHERE COALESCE(person,'')<>''"):
        и = str(r[0])
        if и not in видимые:
            continue
        фио = str(r[1]).strip()
        тел = str(r[4]).strip()
        if not тел and (и, фио.lower()) in тел_из_contact:
            тел = 'в contact'
        люди.setdefault(и, []).append(
            {'fio': фио, 'role': f'{r[2]} {r[3]}'.strip(),
             'phone': тел, 'is_tech': int(r[5] or 0)})
    цб.close()

    итог = Counter()
    строки = []
    for и in видимые:
        л = люди.get(и, [])
        имён = [ч for ч in л if len(str(ч['fio']).split()) >= 2]
        тех = [ч for ч in имён if ч.get('is_tech') or _ТЕХ.search(str(ч['role']))]
        тех_бт = [ч for ч in тех if not str(ч['phone']).strip()]
        итог['видимых'] += 1
        if имён:
            итог['с именами'] += 1
        if тех:
            итог['с техЛПР по имени'] += 1
        if [ч for ч in тех if str(ч['phone']).strip()]:
            итог['техЛПР С телефоном'] += 1
        if тех_бт:
            итог['ЦЕЛЬ: техЛПР без телефона'] += 1
            for ч in тех_бт[:6]:
                строки.append({
                    'inn': и, 'predpriyatie': компании[и][:80],
                    'verdikt': приговор.get(и, ''),
                    'fio': str(ч['fio'])[:60], 'role': str(ч['role'])[:80]})
    строки.sort(key=lambda с: (ВЕС.get(с['verdikt'], 9), с['inn']))
    print(json.dumps(итог.most_common(), ensure_ascii=False, indent=1))
    print(f'строк-целей (человек без телефона): {len(строки)}')
    for с in строки[:12]:
        print(f"  {с['inn']} [{с['verdikt'][:9]:9}] {с['fio'][:28]:28} {с['role'][:40]}")

    if not строки:
        return
    б = io.StringIO()
    в = csv.DictWriter(б, fieldnames=list(строки[0]), delimiter=';',
                       lineterminator='\n')
    в.writeheader()
    в.writerows(строки)
    данные = b'\xef\xbb\xbf' + б.getvalue().encode('utf-8')
    п = os.path.join(r'C:\sender\server', ВЫХОД)
    with open(п, 'wb') as ф:
        ф.write(данные)
        ф.flush()
        os.fsync(ф.fileno())
    try:
        урл = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop')
        urllib.request.urlopen(urllib.request.Request(
            урл.rstrip('/') + '/' + ВЫХОД, data=данные, method='PUT',
            headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}),
            timeout=300).read()
        print(f'на дропе: {ВЫХОД}')
    except Exception as e:  # noqa: BLE001
        print(f'не ушёл на дроп: {str(e)[:80]}')


if __name__ == '__main__':
    main()
