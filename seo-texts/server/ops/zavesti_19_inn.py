# -*- coding: utf-8 -*-
"""Завести карточки предприятиям, которых нет в очереди панели — ДОЛГОВЕЧНО.

ПРОСЬБА 3-Й СЕССИИ, дословно: «19 ИНН из ваших 180 вообще нет в очереди панели.
Заводить карточками — ваше; скажите, когда заведёте, я включу их в цели
обратного хода». Панель моя, значит и заводить мне.

ПЕРЕСЧИТАЛ: их не 19, а 21, и это ДВА РАЗНЫХ СЛУЧАЯ, которые нельзя лечить
одинаково:
  * 20 предприятий нет в `company` вовсе — карточку надо СОЗДАТЬ;
  * 1 предприятие есть, но скрыто (ООО «ОПХ», 7802118578) — его надо РАСКРЫТЬ.
    Завести ему вторую карточку значит посадить дубль, который потом ловить
    чисткой.

КУДА ПИСАТЬ, ЧТОБЫ ПЕРЕЖИЛО ПЕРЕСБОРКУ. Снимок панели `centrifugal.db`
пересобирается: `company`, `contact`, `signal`, `person` дропаются и строятся
заново. Список предприятий сборка берёт НЕ из снимка, а из двух реестров:
`sales_base.json` (centro1) и `centrifugal-core-inns.txt` (centro2); данные
карточки — из `enrich.db` (`companies`, `requisites`, `people`).
Поэтому пишем в ТРИ места:
  1. ИНН — в реестр `centrifugal-core-inns.txt` (иначе предприятие не попадёт
     в следующую сборку вовсе);
  2. реквизиты и людей — в `enrich.db` (иначе карточка соберётся пустой);
  3. и в текущий снимок — чтобы продавец увидел сегодня, а не после пересборки.
Урок 25.07 ровно об этом: результат, записанный только в снимок, откатывается.

ЧЕСТНАЯ ПОМЕТКА. Эти предприятия попали к нам ПО ЧЕЛОВЕКУ, а не по доказанной
машине: их нашёл поиск ЛПР по новостям, протоколам и страницам «Руководство».
Центробежность у них НЕ доказана, и карточка говорит это прямо в поле «чего не
хватает». Молчаливо подмешать их к ядру центробежных было бы враньём в данных.

ДВА ИЗ ДВАДЦАТИ НЕ ЗАВОДИМ. У 5020037784 и 2453013555 из людей только
пиарщик, юрист и «общий» — ни одного технического имени и ни одного факта нашей
машины. Предприятие в очереди продавца без того и другого — это не лид, а
строка, которую он будет пролистывать.

По умолчанию СУХОЙ ПРОГОН. Запуск: python zavesti_19_inn.py [--apply]
"""
import csv
import json
import os
import re
import shutil
import sqlite3
import sys
import time
from collections import Counter, defaultdict

ЦБ = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
ПР = os.getenv('CENTRO_SALES_DB') or r'C:\seostat\data\centro_sales.db'
ENR = os.getenv('CENTRO_ENRICH_DB') or r'C:\sender\enrich.db'
РЕЕСТР = os.getenv('CENTRO_CORE_TXT') or os.path.join(
    r'C:\seostat\drop\drop-storage', 'centrifugal-core-inns.txt')
ЛЮДИ = os.path.join(r'C:\seostat\drop\drop-storage',
                    'DLYA-3S-180-INN-s-imenami.csv')
РЕКВ = os.path.join(r'C:\seostat\drop\drop-storage', 'novye20-rekvizity.json')
ПРИМЕНИТЬ = '--apply' in sys.argv

ТЕХ_РОЛИ = {'гл.инженер', 'гл.энергетик', 'гл.механик', 'гл.технолог',
            'гл.конструктор', 'техдиректор', 'нач.производства', 'нач.цеха',
            'АСУ/КИПиА'}
ИСТОЧНИК = 'заведено по найденному техническому человеку (поиск ЛПР)'
НЕ_ХВАТАЕТ = ('центробежность НЕ доказана: карточка заведена по человеку, '
              'а не по факту машины')


def люди_по_инн():
    csv.field_size_limit(10 ** 7)
    из = defaultdict(list)
    if not os.path.exists(ЛЮДИ):
        return из
    with open(ЛЮДИ, encoding='utf-8-sig', errors='replace', newline='') as ф:
        for r in csv.DictReader(ф, delimiter=';'):
            и = re.sub(r'\D', '', str(r.get('inn') or ''))
            if len(и) in (10, 12):
                из[и].append({'chelovek': (r.get('chelovek') or '').strip(),
                              'dolzhnost': (r.get('dolzhnost') or '').strip(),
                              'rol': (r.get('rol') or '').strip(),
                              'ssylka': (r.get('ssylka') or '').strip()})
    return из


def main():
    все_люди = люди_по_инн()
    рекв = {}
    if os.path.exists(РЕКВ):
        for з in json.load(open(РЕКВ, encoding='utf-8')):
            рекв[str(з.get('inn'))] = з

    цб = sqlite3.connect(f'file:{ЦБ}?mode=ro', uri=True, timeout=20)
    в_панели = {str(r[0]) for r in цб.execute('SELECT inn FROM company')}
    цб.close()
    пр = sqlite3.connect(f'file:{ПР}?mode=ro', uri=True, timeout=20)
    скрытые = {str(r[0]) for r in пр.execute(
        "SELECT COALESCE(inn,'') FROM hidden_item WHERE kind='company'")}
    пр.close()

    нет_вовсе = sorted(и for и in все_люди if и not in в_панели)
    раскрыть = sorted(и for и in все_люди if и in в_панели and и in скрытые)

    заводим, отклонены = [], []
    for и in нет_вовсе:
        тех = [ч for ч in все_люди[и] if ч['rol'] in ТЕХ_РОЛИ]
        (заводим if тех else отклонены).append((и, тех))

    стат = Counter({'ИНН с людьми в файле': len(все_люди),
                    'нет в панели вовсе': len(нет_вовсе),
                    '  ЗАВОДИМ (есть технический человек)': len(заводим),
                    '  не заводим (ни одного технического имени)': len(отклонены),
                    'есть, но скрыто — РАСКРЫТЬ': len(раскрыть)})
    print(json.dumps(стат.most_common(), ensure_ascii=False, indent=1))
    for и, тех in заводим:
        имя = (рекв.get(и) or {}).get('name') or '(имя не добыто)'
        print(f'  + {и} {имя[:40]:40} тех: '
              + '; '.join(f"{ч['rol']}:{ч['chelovek'][:20]}" for ч in тех[:2]))
    for и, _ in отклонены:
        print(f'  - {и} без технических имён — не заводим')

    if not ПРИМЕНИТЬ:
        print('\nсухой прогон. Повторить с --apply')
        return
    if not (заводим or раскрыть):
        print('менять нечего')
        return

    # --- 1. РЕЕСТР: без строки здесь предприятия не будет в следующей сборке
    было_р = set()
    if os.path.exists(РЕЕСТР):
        shutil.copy2(РЕЕСТР, РЕЕСТР + '.bak-' + str(int(time.time())))
        for с in open(РЕЕСТР, encoding='utf-8-sig', errors='replace'):
            м = re.search(r'(?<!\d)(\d{10}|\d{12})(?!\d)', с)
            if м:
                было_р.add(м.group(1))
    новые_р = [и for и, _ in заводим if и not in было_р]
    if новые_р:
        with open(РЕЕСТР, 'a', encoding='utf-8') as ф:
            for и in новые_р:
                ф.write(и + '\n')
            ф.flush()
            os.fsync(ф.fileno())
    print(f'реестр {os.path.basename(РЕЕСТР)}: было {len(было_р)}, '
          f'добавлено {len(новые_р)}')

    # --- 2. enrich.db: реквизиты и люди, иначе карточка соберётся пустой
    ecx = sqlite3.connect(ENR, timeout=120)
    ecx.execute('PRAGMA busy_timeout=120000')
    есть_р = {c[1] for c in ecx.execute('PRAGMA table_info(requisites)')}
    есть_c = {c[1] for c in ecx.execute('PRAGMA table_info(companies)')}
    есть_p = {c[1] for c in ecx.execute('PRAGMA table_info(people)')}
    сейчас = time.strftime('%Y-%m-%dT%H:%M:%S')
    добавлено = Counter()
    for и, тех in заводим:
        д = рекв.get(и) or {}
        зн_р = {'inn': и, 'ogrn': д.get('ogrn'), 'name_short': д.get('name'),
                'name_full': д.get('name'), 'address': д.get('adres'),
                'director': (д.get('direktor') or '').strip(),
                'status': д.get('status'), 'okved_main': д.get('okved'),
                'src': 'dadata: ' + ИСТОЧНИК, 'updated_at': сейчас}
        поля = [к for к in зн_р if к in есть_р]
        if поля and not ecx.execute(
                'SELECT 1 FROM requisites WHERE inn=?', (и,)).fetchone():
            ecx.execute(f'INSERT INTO requisites ({",".join(поля)}) VALUES '
                        f'({",".join("?" * len(поля))})',
                        tuple(зн_р[к] for к in поля))
            добавлено['requisites'] += 1
        зн_c = {'inn': и, 'name': д.get('name'), 'ogrn': д.get('ogrn'),
                'short_name': д.get('name'), 'okved': д.get('okved'),
                'director': (д.get('direktor') or '').strip(),
                'updated_at': сейчас}
        поля = [к for к in зн_c if к in есть_c]
        if поля and not ecx.execute(
                'SELECT 1 FROM companies WHERE inn=?', (и,)).fetchone():
            ecx.execute(f'INSERT INTO companies ({",".join(поля)}) VALUES '
                        f'({",".join("?" * len(поля))})',
                        tuple(зн_c[к] for к in поля))
            добавлено['companies'] += 1
        for ч in все_люди[и]:
            зн_p = {'inn': и, 'person': ч['chelovek'], 'post': ч['dolzhnost'],
                    'role': ч['rol'], 'source': ИСТОЧНИК,
                    'source_url': ч['ssylka'], 'observed_at': сейчас,
                    'updated_at': сейчас}
            поля = [к for к in зн_p if к in есть_p]
            if поля and not ecx.execute(
                    'SELECT 1 FROM people WHERE inn=? AND person=?',
                    (и, ч['chelovek'])).fetchone():
                ecx.execute(f'INSERT INTO people ({",".join(поля)}) VALUES '
                            f'({",".join("?" * len(поля))})',
                            tuple(зн_p[к] for к in поля))
                добавлено['people'] += 1
    ecx.commit()
    ecx.close()
    print('в enrich.db добавлено:', dict(добавлено))

    # --- 3. снимок: чтобы продавец увидел сегодня, а не после пересборки
    коп = ЦБ + '.bak-' + str(int(time.time()))
    shutil.copy2(ЦБ, коп)
    cx = sqlite3.connect(ЦБ, timeout=120)
    cx.execute('PRAGMA busy_timeout=120000')
    кол = {c[1] for c in cx.execute('PRAGMA table_info(company)')}
    зн_общ = {'istochnik_dopolneniya': ИСТОЧНИК, 'chego_ne_hvataet': НЕ_ХВАТАЕТ,
              'base': 'centro2'}
    ряды, поля = [], None
    for и, тех in заводим:
        д = рекв.get(и) or {}
        з = dict(зн_общ, inn=и, predpriyatie=д.get('name') or '',
                 adres=д.get('adres') or '', direktor=(д.get('direktor') or ''),
                 status_egrul=д.get('status') or '', okved=д.get('okved') or '',
                 lyudej_v_baze=len(все_люди[и]), tehnicheskih=len(тех))
        поля = [к for к in з if к in кол]
        ряды.append(tuple(з[к] for к in поля))
    if ряды:
        cx.executemany(f'INSERT INTO company ({",".join(поля)}) VALUES '
                       f'({",".join("?" * len(поля))})', ряды)
    cx.commit()
    стало = cx.execute('SELECT COUNT(*) FROM company').fetchone()[0]
    cx.close()

    снято = 0
    if раскрыть:
        пр = sqlite3.connect(ПР, timeout=60)
        пр.execute('PRAGMA busy_timeout=60000')
        пр.executemany("DELETE FROM hidden_item WHERE kind='company' AND inn=?",
                       [(и,) for и in раскрыть])
        снято = пр.total_changes
        пр.commit()
        пр.close()
    print(json.dumps({'карточек создано': len(ряды), 'скрытий снято': снято,
                      'предприятий в панели стало': стало,
                      'бэкап снимка': os.path.basename(коп)},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
