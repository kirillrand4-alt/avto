# -*- coding: utf-8 -*-
"""ТехЛПР, у которых нет своего номера, но есть телефон компании.

Задача владельца — «телефоны технических ЛПР». Прямой мобильный есть далеко
не у всех: из 259 технических людей базы свой номер стоит у 105. Но для
звонка это НЕ тупик: продажнику достаточно телефона приёмной, чтобы попросить
к аппарату названного человека — а телефон организации у нас массовый, 6542
компании из checko.

То есть строка «Иванов Пётр Сергеевич, главный энергетик, звонить в приёмную
+7 (8352) 73-55-55 и просить его» — рабочий лид, а не полуфабрикат. Раньше
такие люди просто не попадали в выгрузку.

Считаем и кладём файлом:
  * сколько техЛПР без своего номера;
  * у скольких из них есть телефон КОМПАНИИ (то есть звонок собирается уже
    сейчас, без единого запроса наружу);
  * у скольких нет ничего — вот это и есть настоящая очередь на добор.

Запуск: python tehlpr_bez_telefona.py
"""
import csv
import os
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

ПАПКА = r'C:\sender\server'
ИМЯ = 'tehLPR-zvonit-v-priemnuyu.csv'


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
    тех = "','".join(EDB.EnrichDB.TECH_ROLES)

    всего = q("SELECT COUNT(*) FROM people WHERE role IN ('%s')" % тех).fetchone()[0]
    свой = q("SELECT COUNT(*) FROM people WHERE role IN ('%s') "
             "AND phone != '' AND phone IS NOT NULL" % тех).fetchone()[0]
    print(f'технических ЛПР всего: {всего}, со своим номером: {свой}, '
          f'без своего: {всего - свой}')

    строки = q(
        "SELECT p.inn, COALESCE(c.name,''), COALESCE(c.region,''), p.person, "
        "p.post, p.role, COALESCE(p.email,''), p.source, COALESCE(p.source_url,''), "
        "(SELECT GROUP_CONCAT(phone, ' | ') FROM (SELECT phone FROM phone_contacts "
        ' WHERE inn = p.inn LIMIT 3)) '
        'FROM people p LEFT JOIN companies c ON c.inn = p.inn '
        "WHERE p.role IN ('%s') AND (p.phone = '' OR p.phone IS NULL) "
        'ORDER BY p.role, c.name' % тех).fetchall()

    с_компанией = [r for r in строки if (r[9] or '').strip()]
    без_всего = [r for r in строки if not (r[9] or '').strip()]
    print(f'  из них есть телефон КОМПАНИИ: {len(с_компанией)} '
          f'— звонок собирается уже сейчас')
    print(f'  нет вообще никакого телефона: {len(без_всего)} '
          f'— вот это очередь на добор')

    п = os.path.join(ПАПКА, ИМЯ)
    with open(п, 'w', encoding='utf-8-sig', newline='') as ф:
        в = csv.writer(ф, delimiter=';')
        в.writerow(['ИНН', 'компания', 'регион', 'ФИО', 'должность', 'роль',
                    'почта', 'источник', 'ссылка', 'телефон компании'])
        в.writerows(с_компанией)
        ф.flush()
        os.fsync(ф.fileno())
    print(f'{ИМЯ}: {len(с_компанией)} строк')
    try:
        на_дроп(п, ИМЯ)
        print(f'  на дропе: {ИМЯ}')
    except Exception as e:  # noqa: BLE001
        print(f'  на дроп НЕ легло: {str(e)[:120]}')

    print()
    print('=== ПРИМЕРЫ (кому звонить в приёмную и кого просить) ===')
    for r in с_компанией[:12]:
        print(f'  {r[3][:26]:<26} | {r[5]:<14} | {r[1][:24]:<24} | {(r[9] or "")[:26]}')
    print(f'всего {всего}, без своего номера {len(строки)}, '
          f'с телефоном компании {len(с_компанией)}, глухих {len(без_всего)}')


if __name__ == '__main__':
    main()
