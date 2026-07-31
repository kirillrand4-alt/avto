# -*- coding: utf-8 -*-
"""Слияние трёх версий карточки по 375 предприятиям + ЧИНКА привязки номеров.

Три файла: мой исходный, дополненный второй сессией (47 колонок, факты и
приоритет) и дополненный третьей (35 колонок, реквизиты ЕГРЮЛ). Все три —
производные одного, 375 строк, ключ ИНН, поэтому слияние это объединение
колонок, а не строк.

ГЛАВНОЕ, ради чего скрипт написан. В моём исходнике была колонка
`telefony_iz_bazy` — просто список номеров предприятия через разделитель. По
такой колонке НЕЛЬЗЯ понять, чей номер: продавец видит пять телефонов и одну
фамилию рядом и звонит наугад. Это ровно та ошибка, которую мы весь день
ловили у себя в других местах — данные есть, привязка потеряна молча.

Здесь номер и человек живут в одной записи. Формат одной персоны:

    ФИО ~ должность ~ роль ~ номер ~ вид номера ~ источник

Записи разделяются ` || `. Если у человека номера нет, на его месте стоит
`нет номера` — пустое место не выглядит как «номер потерялся».

Номера, которые не удалось привязать ни к кому, идут В ОТДЕЛЬНУЮ колонку
`nomera_bez_vladelca` с пометкой, откуда они. Смешивать их с привязанными
нельзя: тогда весь столбец перестаёт быть доказательством.

Запуск: python merge_382.py
"""
import csv
import io
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

ДРОП = r'C:\seostat\drop\drop-storage'
ПАПКА = r'C:\sender\server'
ИМЯ = 'SVOD-375-OBEDINENNYY.csv'
ФАЙЛЫ = ['SVOD-382-imeyut-i-pokupali-POLNYY.csv',
         'SVOD-382-DOPOLNENO.csv',
         'SVOD382-dopolnen-3-sessiey.csv']

_ДОБ = re.compile(r'\s*(?:доб|вн|внутр|ext)\.?\s*[:№]?\s*[\d\-]+\s*$', re.I)
_ТЕЛ = re.compile(r'(?:\+?7|8)?[\s(\-]*\d{3,5}[\s)\-]*\d[\d\s\-]{5,10}\d')


def д10(т):
    ц = re.sub(r'\D', '', _ДОБ.sub('', str(т or '')))
    return ц[-10:] if len(ц) >= 10 else ''


def вид(ц):
    if not ц:
        return 'нет номера'
    if ц.startswith('9'):
        return 'мобильный'
    return 'городской'


def клч(т):
    return re.sub(r'\s+', ' ', str(т or '').strip().lower()).replace('ё', 'е')


def читать(имя):
    п = os.path.join(ДРОП, имя)
    if not os.path.exists(п):
        print(f'  НЕТ файла {имя}')
        return []
    csv.field_size_limit(10 ** 7)
    return list(csv.DictReader(
        io.StringIO(open(п, encoding='utf-8-sig', errors='replace').read()),
        delimiter=';'))


def на_дроп(путь, имя):
    import urllib.request
    урл = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop')
    зпр = urllib.request.Request(
        урл.rstrip('/') + '/' + имя, data=open(путь, 'rb').read(), method='PUT',
        headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
    with urllib.request.urlopen(зпр, timeout=300) as о:
        return о.read()[:200]


def main():
    db = EDB.EnrichDB()
    q = db.cx.execute
    тех = set(EDB.EnrichDB.TECH_ROLES)

    # ---------- 1. слить колонки трёх файлов по ИНН
    поля = []
    свод = {}
    расхожд = defaultdict(list)
    for имя in ФАЙЛЫ:
        ряды = читать(имя)
        if not ряды:
            continue
        for к in ряды[0].keys():
            if к not in поля:
                поля.append(к)
        for r in ряды:
            инн = (r.get('inn') or '').strip()
            if not инн:
                continue
            з = свод.setdefault(инн, {})
            for к, v in r.items():
                v = (v or '').strip()
                if not v:
                    continue
                if not з.get(к):
                    з[к] = v
                elif клч(з[к]) != клч(v):
                    # оба непустые и разные — сохраняем, а не затираем молча
                    расхожд[к].append(инн)
                    if v not in з[к]:
                        з[к] = з[к] + ' ;; ' + v
        print(f'{имя}: строк {len(ряды)}, колонок {len(ряды[0])}')
    print(f'предприятий после слияния: {len(свод)}, колонок собрано: {len(поля)}')
    if расхожд:
        print('колонки, где источники разошлись (значения склеены через ;;):')
        for к, сп in sorted(расхожд.items(), key=lambda x: -len(x[1]))[:8]:
            print(f'   {len(сп):>4}  {к}')

    # ---------- 2. ЛЮДИ С ПРИВЯЗАННЫМ НОМЕРОМ, заново из базы
    люди = defaultdict(dict)   # инн -> ключ_человека -> запись

    def полож(инн, фио, долж, роль, номер, ист):
        фио = (фио or '').strip()
        if not фио or инн not in свод:
            return
        к = клч(фио)
        з = люди[инн].setdefault(к, {'фио': фио, 'долж': '', 'роль': '',
                                     'ном': set(), 'ист': set()})
        if долж and not з['долж']:
            з['долж'] = долж.strip()
        if роль and not з['роль']:
            з['роль'] = роль.strip()
        ц = д10(номер)
        if ц:
            з['ном'].add(ц)
        if ист:
            з['ист'].add(ист[:40])

    # 2а. из people (там номер стоит У ЧЕЛОВЕКА)
    for инн, фио, пост, роль, тел, ист in q(
            "SELECT inn, person, COALESCE(post,''), COALESCE(role,''), "
            "COALESCE(phone,''), COALESCE(source,'') FROM people").fetchall():
        полож(инн, фио, пост, роль, тел, ист or 'enrich.db')

    # 2б. из phone_contacts, где ЕСТЬ имя — это и есть привязка
    привязано_из_pc = 0
    без_имени = defaultdict(set)
    for инн, тел, фио, роль, ист in q(
            "SELECT inn, phone, COALESCE(person,''), COALESCE(role,''), "
            "COALESCE(source,'') FROM phone_contacts").fetchall():
        if инн not in свод:
            continue
        ц = д10(тел)
        if not ц:
            continue
        if (фио or '').strip():
            полож(инн, фио, '', роль, тел, ист or 'phone_contacts')
            привязано_из_pc += 1
        else:
            без_имени[инн].add((ц, (ист or 'источник не назван')[:30]))
    print(f'номеров привязано к имени из phone_contacts: {привязано_из_pc}')

    # 2в. из колонки второй сессии lyudi_moi_podrobno
    #     формат: ФИО | должность | тел | тел | роль | источник ;; следующий
    из_вт = 0
    for инн, з in свод.items():
        блок = з.get('lyudi_moi_podrobno') or ''
        for кусок in блок.split(';;'):
            ч = [x.strip() for x in кусок.split('|')]
            if not ч or len(ч[0].split()) < 2:
                continue
            телы = [x for x in ч[1:] if д10(x)]
            долж = ч[1] if len(ч) > 1 and not д10(ч[1]) else ''
            for т in (телы or ['']):
                полож(инн, ч[0], долж, '', т, 'Tender.pro (2-я сессия)')
            из_вт += 1
    print(f'людей из lyudi_moi_podrobno: {из_вт}')

    # 2г. из колонок «ФИО (должность)» — номера там нет, но человек есть
    из_фй = 0
    for инн, з in свод.items():
        for кол in ('tehnicheskie_lyudi', 'lyudi_iz_faylov'):
            for кусок in (з.get(кол) or '').split('|'):
                кусок = кусок.strip()
                м = re.match(r'^(.+?)\s*\((.*?)\)\s*$', кусок)
                if not м or len(м.group(1).split()) < 2:
                    continue
                полож(инн, м.group(1), м.group(2), '', '', кол)
                из_фй += 1
    print(f'людей из колонок ФИО (должность): {из_фй}')

    # ---------- 3. сборка
    строки = []
    для_загол = поля + [
        'lyudi_s_privyazannym_nomerom', 'tehnicheskie_s_nomerom',
        'lyudej_vsego_svedeno', 'lyudej_s_nomerom', 'tehnicheskih_s_nomerom',
        'nomera_bez_vladelca', 'nomerov_bez_vladelca']
    итог = {'с_чел': 0, 'с_ном': 0, 'тех_ном': 0, 'безвл': 0}
    for инн in sorted(свод):
        з = свод[инн]
        нар = list(люди.get(инн, {}).values())
        нар.sort(key=lambda x: (bool(x['ном']),
                                x['роль'] in тех or x['роль'] == 'техконтакт',
                                len(x['долж'])), reverse=True)

        def запись(ч):
            ном = sorted(ч['ном'])
            если_ном = ном[0] if ном else ''
            хвост = (' +ещё ' + ','.join(ном[1:])) if len(ном) > 1 else ''
            return (f"{ч['фио']} ~ {ч['долж'] or 'должность не названа'} ~ "
                    f"{ч['роль'] or 'роль не установлена'} ~ "
                    f"{если_ном or 'нет номера'}{хвост} ~ {вид(если_ном)} ~ "
                    f"{';'.join(sorted(ч['ист'])) or 'источник не назван'}")

        все_зап = ' || '.join(запись(ч) for ч in нар)
        техзап = ' || '.join(запись(ч) for ч in нар
                             if (ч['роль'] in тех or ч['роль'] == 'техконтакт')
                             and ч['ном'])
        с_ном = sum(1 for ч in нар if ч['ном'])
        т_ном = sum(1 for ч in нар if ч['ном'] and
                    (ч['роль'] in тех or ч['роль'] == 'техконтакт'))
        # номера предприятия, которые никому не принадлежат
        занято = {ц for ч in нар for ц in ч['ном']}
        свободные = sorted(
            (ц, и) for ц, и in без_имени.get(инн, set()) if ц not in занято)
        безвл = ' | '.join(f'{ц} ({и})' for ц, и in свободные[:8])

        итог['с_чел'] += 1 if нар else 0
        итог['с_ном'] += 1 if с_ном else 0
        итог['тех_ном'] += 1 if т_ном else 0
        итог['безвл'] += len(свободные)
        строки.append([з.get(к, '') for к in поля] +
                      [все_зап, техзап, len(нар), с_ном, т_ном,
                       безвл, len(свободные)])

    путь = os.path.join(ПАПКА, ИМЯ)
    with open(путь, 'w', encoding='utf-8-sig', newline='') as ф:
        в = csv.writer(ф, delimiter=';')
        в.writerow(для_загол)
        в.writerows(строки)
        ф.flush()
        os.fsync(ф.fileno())

    # ---------- 4. числа перечитыванием + ПРОВЕРКА привязки
    n = счел = сном = стех = 0
    плохих = []
    with open(путь, encoding='utf-8-sig', newline='') as ф:
        for r in csv.DictReader(ф, delimiter=';'):
            n += 1
            зап = r['lyudi_s_privyazannym_nomerom']
            if зап.strip():
                счел += 1
                # у каждой записи должно быть ровно 6 полей через ~
                for ч in зап.split(' || '):
                    if ч.count(' ~ ') != 5:
                        плохих.append((r['inn'], ч[:60]))
            if int(r['lyudej_s_nomerom'] or 0):
                сном += 1
            if int(r['tehnicheskih_s_nomerom'] or 0):
                стех += 1
    print()
    print('=== ОБЪЕДИНЁННЫЙ ФАЙЛ, ЧИСЛА ПЕРЕЧИТЫВАНИЕМ ===')
    print(f'  предприятий: {n}, колонок: {len(для_загол)}')
    print(f'  с людьми: {счел}')
    print(f'  где ХОТЯ БЫ ОДИН человек с номером: {сном}')
    print(f'  где технический человек с номером: {стех}')
    print(f'  номеров без владельца отложено: {итог["безвл"]}')
    print(f'  ПРОВЕРКА формата записи (ФИО~долж~роль~номер~вид~источник): '
          f'{"ОК, все записи разбираются" if not плохих else f"СЛОМАНО {len(плохих)}"}')
    for и, ч in плохих[:5]:
        print(f'    {и}  {ч}')
    try:
        на_дроп(путь, ИМЯ)
        print(f'  на дропе: {ИМЯ}')
    except Exception as e:  # noqa: BLE001
        print(f'  на дроп НЕ легло: {str(e)[:120]}')


if __name__ == '__main__':
    main()
