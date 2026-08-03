# -*- coding: utf-8 -*-
"""Сколько в базе ОБЩИХ номеров, выданных за личные, и кто их принёс.

ЗАЧЕМ. Обратный ход на первых же 25 записях выдал 16 ошибок: номер учебного
центра приписан четверым разным людям на трёх ИНН, федеральный 8-800 — семи
ИНН, номер с краеведческой страницы библиотеки — двоим. То есть 64% улова были
общие номера под видом личных. Третья сессия гонит тот же обратный ход с утра
и записала 156 телефонов; вторая сессия льёт свои. Значит проверять надо не
свой кусок, а ВСЮ базу и по единому правилу.

ПРАВИЛО. Личный номер не может принадлежать двум разным людям и тем более двум
разным предприятиям. Считаем по десяти цифрам, отдельно по каждому хранилищу:
  * `phone_contacts` в enrich.db — куда пишут все каналы обогащения;
  * `contact` в базе панели — то, что видит продавец.
Ничего не удаляем: это ЗАМЕР, чтобы решать, чью выдачу чистить.

ЧТО НЕ СЧИТАЕТСЯ ОШИБКОЙ. Один номер на нескольких людей ОДНОГО предприятия
бывает законно: приёмная, общий коммутатор, отдел. Такие записи вредны только
если помечены как личные (есть ФИО и техническая роль) — их и считаем
отдельной, самой дорогой строкой.

Запуск: python audit_obshchih_nomerov.py [--fajl]
"""
import csv
import json
import os
import re
import sqlite3
import sys
import urllib.request
from collections import Counter, defaultdict

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

ЦБ = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
ФАЙЛ = '--fajl' in sys.argv
ИМЯ = 'AUDIT-obshchie-nomera.csv'
ТЕХ = set(EDB.EnrichDB.TECH_ROLES) | {'техконтакт'}
_ДОБ = re.compile(r'\s*(?:доб|вн|внутр|ext)\.?\s*[:№]?\s*[\d\-]+\s*$', re.I)


def д10(т):
    ц = re.sub(r'\D', '', _ДОБ.sub('', str(т or '')))
    return ц[-10:] if len(ц) >= 10 else ''


def клч(т):
    return re.sub(r'\s+', ' ', str(т or '').strip().lower()).replace('ё', 'е')


def разбор(строки, имя_хранилища):
    """строки: (инн, номер, человек, роль, источник)"""
    по_номеру = defaultdict(lambda: {'инн': set(), 'люди': set(),
                                     'ист': Counter(), 'ряды': []})
    for инн, ном, чел, роль, ист in строки:
        ц = д10(ном)
        if not ц:
            continue
        з = по_номеру[ц]
        з['инн'].add(str(инн))
        if клч(чел):
            з['люди'].add(клч(чел))
        з['ист'][(ист or 'источник не указан')[:46]] += 1
        з['ряды'].append((str(инн), ном, чел, роль, ист))

    итог = Counter()
    виновники = Counter()
    примеры = []
    для_файла = []
    for ц, з in по_номеру.items():
        чужой_инн = len(з['инн']) > 1
        много_людей = len(з['люди']) > 1
        if not (чужой_инн or много_людей):
            continue
        тех_личных = sum(1 for _и, _н, ч, р, _ист in з['ряды']
                         if клч(ч) and р in ТЕХ)
        вид = ('номер на разных ПРЕДПРИЯТИЯХ' if чужой_инн
               else 'номер на разных людях одного предприятия')
        итог[вид] += len(з['ряды'])
        if тех_личных:
            итог['из них помечены как ЛИЧНЫЙ ТЕХНИЧЕСКИЙ'] += тех_личных
        for ист, n in з['ист'].items():
            виновники[ист] += n
        if len(примеры) < 12 and чужой_инн:
            примеры.append(
                f'  {ц}: {len(з["инн"])} ИНН, {len(з["люди"])} людей — '
                + '; '.join(f'{и} {(ч or "?")[:20]}' for и, _н, ч, _р, _ист
                            in з['ряды'][:4]))
        for и, ном, ч, р, ист in з['ряды']:
            для_файла.append([имя_хранилища, ц, и, ном, ч, р, ист, вид])
    return итог, виновники, примеры, для_файла


def main():
    db = EDB.EnrichDB()
    из_enrich = list(db.cx.execute(
        "SELECT inn, phone, COALESCE(person,''), COALESCE(role,''), "
        "COALESCE(source,'') FROM phone_contacts"))
    цб = sqlite3.connect(f'file:{ЦБ}?mode=ro', uri=True, timeout=20)
    из_панели = list(цб.execute(
        "SELECT inn, value, COALESCE(person,''), COALESCE(role,''), "
        "COALESCE(source,'') FROM contact WHERE kind='phone'"))
    цб.close()

    файл = []
    for строки, имя in ((из_enrich, 'enrich.db/phone_contacts'),
                        (из_панели, 'панель/contact')):
        итог, виновники, примеры, дф = разбор(строки, имя)
        файл += дф
        print(f'=== {имя}: всего записей {len(строки)}')
        print(json.dumps(итог.most_common(), ensure_ascii=False, indent=1))
        print('  кто принёс (по числу подозрительных записей):')
        for ист, n in виновники.most_common(8):
            print(f'    {n:>5}  {ист}')
        for п in примеры[:6]:
            print(п)
        print()

    if not (ФАЙЛ and файл):
        return
    п = os.path.join(r'C:\sender\server', ИМЯ)
    with open(п, 'w', encoding='utf-8-sig', newline='') as ф:
        в = csv.writer(ф, delimiter=';')
        в.writerow(['hranilishche', 'nomer10', 'inn', 'nomer', 'chelovek',
                    'rol', 'istochnik', 'vid_oshibki'])
        в.writerows(файл)
    try:
        урл = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop')
        urllib.request.urlopen(urllib.request.Request(
            урл.rstrip('/') + '/' + ИМЯ, data=open(п, 'rb').read(),
            method='PUT',
            headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}),
            timeout=300).read()
        print(f'файл на дропе: {ИМЯ} ({len(файл)} строк)')
    except Exception as e:  # noqa: BLE001
        print(f'файл не ушёл на дроп: {e}')


if __name__ == '__main__':
    main()
