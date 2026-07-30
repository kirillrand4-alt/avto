# -*- coding: utf-8 -*-
"""Список целей для поиска техЛПР: там, где его нет, а повод звонить есть.

Собирает файл целей для `lpr_serp --targets`, чтобы не переписывать общий
`newsco_targets.jsonl` (он один на две сессии).

Две очереди, в порядке приоритета владельца:
  1. **Глухие техЛПР** — человек известен по имени и должности, но телефона
     нет ни своего, ни компании. Таких 34, и это штучная работа.
  2. **Предприятия с планом закупки 223-ФЗ** — 129 штук, у них намерение
     задокументировано ведомственным реестром, а технического ЛПР ноль. Это
     главный фронт: звонить есть о чём, но некому.

Порядок внутри — по выручке: при равном отсутствии контакта крупное
предприятие важнее.

Запуск: python celi_bez_tehlpr.py [--out ФАЙЛ] [--kogo plan|gluhie|oba]
"""
import json
import os
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

ВЫХОД = (sys.argv[sys.argv.index('--out') + 1] if '--out' in sys.argv
         else r'C:\seostat\drop\celi_bez_tehlpr.jsonl')
КОГО = (sys.argv[sys.argv.index('--kogo') + 1] if '--kogo' in sys.argv else 'oba')


def main():
    db = EDB.EnrichDB()
    q = db.cx.execute
    тех = "','".join(EDB.EnrichDB.TECH_ROLES)

    # 1. глухие: техЛПР без своего и без телефона компании
    глухие = [r[0] for r in q(
        "SELECT DISTINCT p.inn FROM people p WHERE p.role IN ('%s') "
        "AND (p.phone='' OR p.phone IS NULL) "
        'AND p.inn NOT IN (SELECT inn FROM phone_contacts)' % тех).fetchall()]

    # 2. план закупки без единого техЛПР
    план = [r[0] for r in q(
        "SELECT DISTINCT inn FROM signals WHERE source='ЕИС план 223-ФЗ' "
        "AND inn NOT IN (SELECT inn FROM people WHERE role IN ('%s'))" % тех).fetchall()]

    print(f'глухих техЛПР (компаний): {len(глухие)}')
    print(f'предприятий с планом и без техЛПР: {len(план)}')

    # наём в техслужбу: 447 компаний, у 437 нет техЛПР. Многие пришли из
    # hh-инверсии и в карточке несут только ИНН — им нужен dadata за
    # названием, адресом и руководителем.
    наём = [r[0] for r in q(
        "SELECT DISTINCT inn FROM signals WHERE event_type='наём в техслужбу'"
    ).fetchall()]
    print(f'компаний с наймом в техслужбу: {len(наём)}')
    if КОГО == 'nayom':
        хочу = наём
    else:
        хочу = []
    if КОГО in ('oba', 'gluhie'):
        хочу += глухие
    if КОГО in ('oba', 'plan'):
        хочу += [и for и in план if и not in set(глухие)]
    if not хочу:
        print('целей нет')
        return

    сп = ','.join('?' * len(хочу))
    строки = q(
        'SELECT inn, name, okved, region, COALESCE(revenue_rub, 0) '
        f'FROM companies WHERE inn IN ({сп})', хочу).fetchall()
    # выручка вниз: при равном отсутствии контакта крупное важнее
    строки.sort(key=lambda r: -(r[4] or 0))

    with open(ВЫХОД, 'w', encoding='utf-8') as ф:
        for инн, имя, оквэд, регион, выр in строки:
            ф.write(json.dumps({
                'inn': инн, 'krat': (имя or '')[:60], 'poln': имя or '',
                'okved': оквэд or '',
                # `city` И `region` ОБА: lpr_serp обращался к 'city' жёстко и
                # падал KeyError на моём файле целей, где был только регион.
                # Три круга ушли с кодом 1, а обёртка печатала пустоту.
                'region': регион or '', 'city': регион or '',
                'revenue_rub': выр or 0}, ensure_ascii=False) + '\n')
        ф.flush()
        os.fsync(ф.fileno())
    print(f'{ВЫХОД}: {len(строки)} целей')

    # сколько из них пройдут фильтр «обрабатывающие производства 10-33»,
    # который lpr_serp применяет по умолчанию — иначе цифра выхода обманет
    производство = 0
    for _и, _н, оквэд, _р, _в in строки:
        ц = (оквэд or '').strip()
        num = ''
        for c in ц:
            if c.isdigit():
                num += c
            else:
                break
        if num and 10 <= int(num) <= 33:
            производство += 1
    print(f'из них обрабатывающих производств (ОКВЭД 10-33): {производство}')
    print(f'  остальные {len(строки) - производство} lpr_serp пропустит с '
          'фильтром по умолчанию — для них нужен --vse')
    # Соседняя сессия просила именно этот список: она прогонит вложения
    # техзаданий по нашим плановым предприятиям первыми, а не по общей
    # очереди. Отдаём с поводом и признаком «есть ли вообще телефон».
    import csv
    п = r'C:\sender\server\plan-223-inn-dlya-soseda.csv'
    сп2 = ','.join('?' * len(план))
    ряды = q(
        'SELECT s.inn, COALESCE(c.name, %s), COALESCE(c.region, %s), '
        's.event_type, s.what, s.sum, s.source_url, '
        '(SELECT COUNT(*) FROM phone_contacts f WHERE f.inn = s.inn) '
        "FROM signals s LEFT JOIN companies c ON c.inn = s.inn "
        "WHERE s.source='ЕИС план 223-ФЗ' ORDER BY s.ts" % ("''", "''")).fetchall()
    with open(п, 'w', encoding='utf-8-sig', newline='') as ф:
        в = csv.writer(ф, delimiter=';')
        в.writerow(['ИНН', 'компания', 'регион', 'когда план', 'предмет',
                    'сумма', 'ссылка', 'телефонов в базе'])
        в.writerows(ряды)
        ф.flush()
        os.fsync(ф.fileno())
    try:
        import urllib.request
        урл = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop')
        зпр = urllib.request.Request(
            урл.rstrip('/') + '/plan-223-inn-dlya-soseda.csv',
            data=open(п, 'rb').read(), method='PUT',
            headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
        urllib.request.urlopen(зпр, timeout=180).read()
        print(f'на дропе: plan-223-inn-dlya-soseda.csv ({len(ряды)} строк)')
    except Exception as e:  # noqa: BLE001
        print(f'на дроп НЕ легло: {str(e)[:120]}')
    без = sum(1 for r in ряды if not r[7])
    print(f'  из них без единого телефона: {без}')
    print(f'целей {len(строки)}, производств {производство}')


if __name__ == '__main__':
    main()
