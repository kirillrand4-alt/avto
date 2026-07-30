# -*- coding: utf-8 -*-
"""Выгрузки на дроп для параллельной сессии: люди Ростехнадзора и все техЛПР.

Просьба соседней сессии 30.07: «на дропе лежит только скрипт `rtn_znaniya.py`,
сопоставлять нечего». Справедливо — я выложил инструмент и не выложил
результат. Сопоставление графиков проверки знаний с их 246 воздушными
предприятиями и 683 водоканалами они взяли на себя, и без этой выгрузки оно
не начнётся.

Кладём два файла:
  * `rtn-lyudi.csv` — всё, что дал источник «РТН: проверка знаний»;
  * `nashi-tehLPR.csv` — все технические ЛПР базы со всеми источниками, чтобы
    сосед мог сверять не только Ростехнадзор.

Имена файлов на дропе ЗАДАНЫ ЯВНО. Третья за час коллизия одного вида на две
сессии (id задания из секунды и pid; имя от `fetch_url` по последнему сегменту
URL; слипшиеся пачки) — общий признак один: уникальность имени нигде не
проверяется, а потеря молчаливая.

Запуск: python vygruzka_dlya_soseda.py
"""
import csv
import os
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

РТН = 'РТН: проверка знаний'
ПАПКА = r'C:\sender\server'


def на_дроп(путь, имя):
    import urllib.request
    урл = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop')
    зпр = urllib.request.Request(
        урл.rstrip('/') + '/' + имя, data=open(путь, 'rb').read(), method='PUT',
        headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
    with urllib.request.urlopen(зпр, timeout=180) as о:
        return о.read()[:200]


def выгрузить(имя, шапка, строки):
    п = os.path.join(ПАПКА, имя)
    with open(п, 'w', encoding='utf-8-sig', newline='') as ф:
        в = csv.writer(ф, delimiter=';')
        в.writerow(шапка)
        в.writerows(строки)
        ф.flush()
        os.fsync(ф.fileno())
    print(f'{имя}: {len(строки)} строк')
    try:
        на_дроп(п, имя)
        print(f'  на дропе: {имя}')
    except Exception as e:  # noqa: BLE001
        print(f'  на дроп НЕ легло: {str(e)[:120]}')
    return len(строки)


def main():
    db = EDB.EnrichDB()
    q = db.cx.execute
    тех = "','".join(EDB.EnrichDB.TECH_ROLES)

    ртн = q(
        'SELECT p.inn, COALESCE(c.name, %s), p.person, p.post, p.role, '
        'p.phone, p.email, p.observed_at, p.source_url '
        'FROM people p LEFT JOIN companies c ON c.inn = p.inn '
        'WHERE p.source = ? ORDER BY p.role, p.inn' % "''", (РТН,)).fetchall()
    n1 = выгрузить('rtn-lyudi.csv',
                   ['ИНН', 'компания', 'ФИО', 'должность', 'роль', 'телефон',
                    'почта', 'дата аттестации', 'источник'], ртн)
    тех_ртн = sum(1 for r in ртн if r[4] in EDB.EnrichDB.TECH_ROLES)
    print(f'  из них технических: {тех_ртн}, компаний: {len({r[0] for r in ртн})}')

    все = q(
        'SELECT p.inn, COALESCE(c.name, %s), c.region, p.person, p.post, '
        'p.role, p.phone, p.email, p.source, p.source_url '
        'FROM people p LEFT JOIN companies c ON c.inn = p.inn '
        "WHERE p.role IN ('%s') ORDER BY p.role, p.inn" % ("''", тех)).fetchall()
    n2 = выгрузить('nashi-tehLPR.csv',
                   ['ИНН', 'компания', 'регион', 'ФИО', 'должность', 'роль',
                    'телефон', 'почта', 'источник', 'ссылка'], все)
    с_тел = sum(1 for r in все if (r[6] or '').strip())
    print(f'  из них с телефоном: {с_тел}, компаний: {len({r[0] for r in все})}')

    print()
    print('=== ИСТОЧНИКИ ТЕХЛПР (из базы) ===')
    for и, n in q(
            "SELECT source, COUNT(*) FROM people WHERE role IN ('%s') "
            'GROUP BY source ORDER BY 2 DESC' % тех).fetchall():
        print(f'  {n:>4}  {и or "(без источника)"}')
    print(f'ртн {n1}, техЛПР {n2}')


if __name__ == '__main__':
    main()
