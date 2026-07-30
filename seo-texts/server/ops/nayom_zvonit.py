# -*- coding: utf-8 -*-
"""Кому звонить по поводу «у вас ищут человека в техслужбу».

Самый крупный необработанный пул дня: 542 сигнала «наём в техслужбу» в 447
компаниях, и у 437 из них технического ЛПР в базе нет вовсе. Но отсутствие
ИМЕНИ не значит отсутствие ЗВОНКА: если у компании есть телефон, разговор
уже складывается — «у вас открыта вакансия машиниста компрессорных
установок, пока её закрывают, кто ведёт компрессорную?»

Вакансия сильна тем, что говорит сразу две вещи: служба существует (значит
есть что эксплуатировать) и в ней прямо сейчас дыра.

Считаем из базы и кладём файлом на дроп.

Запуск: python nayom_zvonit.py
"""
import csv
import os
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

ИМЯ = 'nayom-v-tehsluzhbu.csv'
ПАПКА = r'C:\sender\server'


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

    ряды = q(
        "SELECT s.inn, COALESCE(c.name,''), COALESCE(c.region,''), "
        "COALESCE(c.site,''), s.what, s.source_url, "
        '(SELECT GROUP_CONCAT(phone, \' | \') FROM (SELECT phone FROM '
        ' phone_contacts f WHERE f.inn = s.inn LIMIT 3)), '
        '(SELECT COUNT(*) FROM people p WHERE p.inn = s.inn), '
        f"(SELECT COUNT(*) FROM people p WHERE p.inn = s.inn AND p.role IN ('{тех}')) "
        'FROM signals s LEFT JOIN companies c ON c.inn = s.inn '
        "WHERE s.event_type = 'наём в техслужбу' "
        'GROUP BY s.inn ORDER BY c.name').fetchall()

    всего = len(ряды)
    с_тел = [r for r in ряды if (r[6] or '').strip()]
    без_тел = [r for r in ряды if not (r[6] or '').strip()]
    с_техлпр = [r for r in ряды if r[8]]
    с_кем_то = [r for r in ряды if r[7]]
    print(f'компаний с наймом в техслужбу: {всего}')
    print(f'  с телефоном — звонить можно сейчас: {len(с_тел)}')
    print(f'  без телефона: {len(без_тел)}')
    print(f'  уже есть техЛПР: {len(с_техлпр)}, есть хоть какой-то человек: '
          f'{len(с_кем_то)}')
    print(f'  с сайтом (можно обойти за людьми): '
          f'{sum(1 for r in ряды if (r[3] or "").strip())}')

    п = os.path.join(ПАПКА, ИМЯ)
    with open(п, 'w', encoding='utf-8-sig', newline='') as ф:
        в = csv.writer(ф, delimiter=';')
        в.writerow(['ИНН', 'компания', 'регион', 'сайт', 'вакансия (повод)',
                    'ссылка', 'телефоны', 'людей в базе', 'из них техЛПР'])
        # сначала те, кому можно звонить прямо сейчас
        в.writerows(с_тел + без_тел)
        ф.flush()
        os.fsync(ф.fileno())
    print(f'{ИМЯ}: {всего} строк')
    try:
        на_дроп(п, ИМЯ)
        print(f'  на дропе: {ИМЯ}')
    except Exception as e:  # noqa: BLE001
        print(f'  на дроп НЕ легло: {str(e)[:120]}')

    print()
    print('=== КОМУ ЗВОНИТЬ ПРЯМО СЕЙЧАС (примеры) ===')
    for r in с_тел[:12]:
        print(f'  {r[1][:26]:<26} | {(r[6] or "")[:20]:<20} | {(r[4] or "")[:44]}')
    print(f'всего {всего}, с телефоном {len(с_тел)}, без {len(без_тел)}')


if __name__ == '__main__':
    main()
