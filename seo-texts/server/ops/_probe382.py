# -*- coding: utf-8 -*-
"""Разведка: почему в своде 382 мало техлюдей и мало попаданий в базу обзвона."""
import csv
import glob
import io
import os
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

ДРОП = r'C:\seostat\drop\drop-storage'


def main():
    csv.field_size_limit(10 ** 7)
    инн = set()
    for имя in ('IMEYUT-198-vozdushnye-centrobezhnye.csv',
                'POKUPALI-RANEE-184-vozdushnye-centrobezhnye.csv'):
        п = os.path.join(ДРОП, имя)
        for r in csv.DictReader(io.StringIO(
                open(п, encoding='utf-8-sig', errors='replace').read()),
                delimiter=';'):
            и = (r.get('inn') or '').strip()
            if и:
                инн.add(и)
    print('ИНН уникальных:', len(инн))
    пример = sorted(инн)[:5]
    print('примеры ИНН:', пример)

    db = EDB.EnrichDB()
    q = db.cx.execute
    тех = set(EDB.EnrichDB.TECH_ROLES)
    вн = "','".join(инн)
    вс = q(f"SELECT COUNT(*) FROM people WHERE inn IN ('{вн}')").fetchone()[0]
    тл = q(f"SELECT COUNT(*) FROM people WHERE inn IN ('{вн}') AND "
           f"role IN ('{chr(39).join([])}')".replace("IN ('')", "IN ('%s')" %
                                                     "','".join(тех))).fetchone()[0]
    print(f'людей в people по этим ИНН: {вс}, из них техроль: {тл}')
    print('роли, топ:')
    for роль, n in q(f"SELECT COALESCE(role,''), COUNT(*) FROM people "
                     f"WHERE inn IN ('{вн}') GROUP BY role "
                     'ORDER BY 2 DESC LIMIT 10').fetchall():
        print(f'   {n:>5}  {роль}')

    # база обзвона: как называется колонка ИНН
    файлы = sorted(glob.glob(os.path.join(ДРОП, 'obzvon_all*.csv')))
    print('файлы обзвона:', [os.path.basename(x) for x in файлы])
    if файлы:
        with open(файлы[0], encoding='utf-8-sig', errors='replace',
                  newline='') as f:
            рд = csv.DictReader(f, delimiter=';')
            поля = рд.fieldnames
            print('колонок:', len(поля or []))
            print('колонки:', поля)
            вид = 0
            for i, r in enumerate(рд):
                if i > 400000:
                    break
                вид += 1
            print('строк прочитано:', вид)


if __name__ == '__main__':
    main()
