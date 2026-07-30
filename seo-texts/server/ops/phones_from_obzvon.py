# -*- coding: utf-8 -*-
"""Телефоны из выгрузки обзвона тем компаниям базы, у кого их нет.

Наводка владельца 30.07: «чеко есть в базе обзвона, где 160к контактов,
посмотри там». И он прав — я собирался идти на checko сетью за тем, что уже
лежит файлом на сервере.

Выгрузка обзвона несёт колонку телефонов (индекс 18, значения через «|»), и
это ровно тот же checko, только уже скачанный. Сетевой проход по сотням
компаний заменяется одним чтением файла: ни капчи, ни прокси, ни лимитов.

Пишем ТОЛЬКО тем, у кого телефона в базе нет вовсе, и только через
`EDB.add_phone` — он и нормализует, и отсекает реквизиты компании, и не
роняет уже известную роль до «общий». Роль тут честно пустая: выгрузка даёт
номер организации, а не человека.

Запуск: python phones_from_obzvon.py [--dry] [--only-plan]
  --only-plan — только предприятия с планом закупки 223-ФЗ (проверить выход
                на узкой выборке, прежде чем идти по всей базе)
"""
import csv
import os
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB       # noqa: E402
import enrich_contacts as EC  # noqa: E402

СУХОЙ = '--dry' in sys.argv
ТОЛЬКО_ПЛАН = '--only-plan' in sys.argv
ИСТОЧНИК = 'обзвон/checko'
ИНН, ПОЛН, КРАТ, ТЕЛ, САЙТ = 1, 6, 5, 18, 20


def main():
    db = EDB.EnrichDB()
    q = db.cx.execute
    if ТОЛЬКО_ПЛАН:
        цели = [r[0] for r in q(
            "SELECT DISTINCT inn FROM signals WHERE source='ЕИС план 223-ФЗ' "
            'AND inn NOT IN (SELECT inn FROM phone_contacts)').fetchall()]
    else:
        цели = [r[0] for r in q(
            'SELECT inn FROM companies WHERE inn NOT IN '
            '(SELECT inn FROM phone_contacts)').fetchall()]
    print(f'компаний БЕЗ телефона в базе: {len(цели)}')
    sys.stdout.flush()
    if not цели:
        print('нечего делать')
        return

    путь = EC._get_base()
    if not путь:
        raise SystemExit('выгрузка обзвона не найдена')
    print(f'выгрузка: {путь}')
    sys.stdout.flush()

    ждём = set(цели)
    найдено = {}
    строк = 0
    try:
        csv.field_size_limit(2 ** 18)
    except Exception:  # noqa: BLE001
        pass
    with open(путь, encoding='utf-8-sig', newline='') as ф:
        for row in csv.reader(ф, delimiter=';'):
            строк += 1
            if len(row) <= ТЕЛ:
                continue
            и = (row[ИНН] or '').strip()
            if и not in ждём:
                continue
            тел = [x.strip() for x in (row[ТЕЛ] or '').split('|') if x.strip()]
            if тел:
                найдено[и] = (тел, (row[ПОЛН] or row[КРАТ] or '').strip(),
                              (row[САЙТ] or '').strip())
            ждём.discard(и)
            if not ждём:
                break
    print(f'прочитано строк выгрузки: {строк}')
    print(f'из {len(цели)} компаний нашлось в выгрузке с телефоном: {len(найдено)}')
    sys.stdout.flush()

    было = q('SELECT COUNT(*) FROM phone_contacts').fetchone()[0]
    записано = 0
    if not СУХОЙ:
        for и, (тел, имя, сайт) in найдено.items():
            for т in тел[:6]:
                try:
                    if db.add_phone(и, т, source=ИСТОЧНИК):
                        записано += 1
                except Exception as e:  # noqa: BLE001
                    print(f'  {и}: {str(e)[:70]}')
    стало = q('SELECT COUNT(*) FROM phone_contacts').fetchone()[0]

    print()
    print('=== ИЗ БАЗЫ (не из счётчиков прогона) ===')
    print(f'  телефоны: было {было} → стало {стало} (+{стало - было})')
    сколько = q(
        'SELECT COUNT(DISTINCT inn) FROM phone_contacts WHERE source=?',
        (ИСТОЧНИК,)).fetchone()[0]
    print(f'  компаний с телефоном источника «{ИСТОЧНИК}»: {сколько}')
    без = q('SELECT COUNT(*) FROM companies WHERE inn NOT IN '
            '(SELECT inn FROM phone_contacts)').fetchone()[0]
    print(f'  компаний БЕЗ телефона осталось: {без}')
    print(f'целей {len(цели)}, нашлось {len(найдено)}, записано {записано}')


if __name__ == '__main__':
    main()
