# -*- coding: utf-8 -*-
"""Мои личные номера в общем формате — для сведения трёх сессий в ОДНО число.

Три сессии назвали свои счёта: 232 номера на 32 предприятиях (третья), 210 на
30 (вторая), 84 личных на 19 (я). Сверка по ИНН показала, что предприятия у
нас почти одни и те же: из её 32 у меня есть 29, пересечение по Тендер.Про
31 из 32. Значит сумма 526 была бы приписками втрое.

Честное общее число получается только сложением САМИХ НОМЕРОВ с дедупом по
десяти цифрам — по предприятиям складывать нельзя. Формат общий:
inn;fio;dolzhnost;nomer_10cifr;rol;istochnik.

Что считаю ЛИЧНЫМ номером (мера третьей сессии, я её принял):
  * мобильный код 9xx после +7 или 8;
  * НЕ 8-800 — это общий номер, а не человека;
  * НЕ служебная линия: номер, встречающийся у трёх и более разных компаний
    (её же правило; у меня таких 63, и ни один не попал к техническим людям);
  * добавочный отрезается ДО нормализации — иначе последние десять цифр
    съезжают на хвост добавочного и живой номер выглядит мусором. На этом я
    сегодня чуть не снёс 141 настоящий номер.

Запуск: python lichnye_nomera.py
"""
import csv
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

ИМЯ = 'LICHNYE-NOMERA-1-SESSIYA.csv'
ПАПКА = r'C:\sender\server'
_ДОБ = re.compile(r'\s*(?:доб|вн|внутр|ext)\.?\s*[:№]?\s*[\d\-]+\s*$', re.I)
_МОБ = re.compile(r'(?:\+?7|8)\D{0,3}9\d\d')
_800 = re.compile(r'8\D{0,3}800')


def д10(т):
    ц = re.sub(r'\D', '', _ДОБ.sub('', т or ''))
    return ц[-10:] if len(ц) >= 10 else ''


def личный(т):
    return bool(_МОБ.search(т or '')) and not _800.search(т or '')


def на_дроп(путь, имя):
    import urllib.request
    урл = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop')
    зпр = urllib.request.Request(
        урл.rstrip('/') + '/' + имя, data=open(путь, 'rb').read(), method='PUT',
        headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
    with urllib.request.urlopen(зпр, timeout=180) as о:
        return о.read()[:200]


def main():
    db = EDB.EnrichDB()
    q = db.cx.execute
    тр = "','".join(EDB.EnrichDB.TECH_ROLES)

    # служебные линии по правилу третьей сессии: номер у 3+ разных компаний
    раскид = defaultdict(set)
    for инн, тел in q('SELECT inn, phone FROM phone_contacts').fetchall():
        ц = д10(тел)
        if ц:
            раскид[ц].add(инн)
    служебные = {ц for ц, s in раскид.items() if len(s) >= 3}
    print(f'служебных линий (3+ компаний): {len(служебные)}')

    строки = []
    видели = set()
    # 1) номер, стоящий у самого человека
    for инн, фио, пост, роль, тел in q(
            "SELECT inn, person, COALESCE(post,''), role, COALESCE(phone,'') "
            f"FROM people WHERE role IN ('{тр}') OR role='техконтакт'").fetchall():
        ц = д10(тел)
        if not (ц and личный(тел)) or ц in служебные:
            continue
        if (инн, ц) in видели:
            continue
        видели.add((инн, ц))
        строки.append([инн, фио, пост, ц, роль, 'people'])
    из_people = len(строки)

    # 2) номер человека из phone_contacts, если у него он там, а в people нет
    for инн, фио, тел, ист in q(
            "SELECT inn, COALESCE(person,''), phone, COALESCE(source,'') "
            "FROM phone_contacts WHERE person != ''").fetchall():
        ц = д10(тел)
        if not (ц and личный(тел)) or ц in служебные or (инн, ц) in видели:
            continue
        роль = (q("SELECT role FROM people WHERE inn=? AND person=?",
                  (инн, фио)).fetchone() or ('',))[0]
        if роль not in EDB.EnrichDB.TECH_ROLES and роль != 'техконтакт':
            continue
        видели.add((инн, ц))
        строки.append([инн, фио, '', ц, роль, 'phone_contacts:' + ист[:30]])

    путь = os.path.join(ПАПКА, ИМЯ)
    with open(путь, 'w', encoding='utf-8-sig', newline='') as ф:
        в = csv.writer(ф, delimiter=';')
        в.writerow(['inn', 'fio', 'dolzhnost', 'nomer_10cifr', 'rol', 'istochnik'])
        в.writerows(строки)
        ф.flush()
        os.fsync(ф.fileno())

    print(f'{ИМЯ}: {len(строки)} строк')
    print(f'  из них номер стоял у человека в people: {из_people}')
    print(f'  добрано из phone_contacts того же человека: {len(строки) - из_people}')
    print(f'  предприятий: {len({с[0] for с in строки})}')
    print(f'  разных номеров: {len({с[3] for с in строки})}')
    try:
        на_дроп(путь, ИМЯ)
        print(f'  на дропе: {ИМЯ}')
    except Exception as e:  # noqa: BLE001
        print(f'  на дроп НЕ легло: {str(e)[:120]}')
    print()
    for с in строки[:10]:
        print(f'  {с[0]}  {с[1][:26]:<26} {с[4]:<12} {с[3]}  {с[5][:22]}')
    print(f'личных {len(строки)}, предприятий {len({с[0] for с in строки})}')


if __name__ == '__main__':
    main()
