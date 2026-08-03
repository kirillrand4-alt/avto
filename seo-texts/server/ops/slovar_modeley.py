# -*- coding: utf-8 -*-
"""Словарь ВСЕХ марок, встреченных в базе: что это за машина и какая среда.

Пункт 9 владельца из VSEM-SESSIYAM: «запишите все уже известные нам модели
центробежных компрессоров которые встречались за всё время, и используйте их
для опознавания среды, подходит нам компания или нет, а также прогона по
площадкам».

ПОЧЕМУ СЛОВАРЬ, А НЕ РЕГУЛЯРКА В КАЖДОМ ОПЕ. Сейчас каждый канал решает
«наша ли машина» сам: доливка ЭПБ по одному правилу, скрытие непрофильных по
другому, суд моделей по третьему. Одна и та же марка в разных местах получает
разный ответ, и разойтись они могут молча. Словарь — одно место, где ответ
записан и проверяем, и он же список слов для прогона по площадкам.

ЧЕМ ОПОЗНАЁМ. `centro_marki.razobrat` — паспортная таблица плюс семейства
обозначений. Он даёт ТИП и СРЕДУ, а признак `nash_profil` уже учитывает, что
центробежная машина на газу нам не подходит (нагнетатели ГПА Н-370, НЦ-16).
Чего справочник не знает — не выдумываем: такие марки уходят в отдельный файл
с частотой, и по ним отдельный проход провайдером.

ВАЖНО ПРО ЧАСТОТУ. Считаем и упоминания, и ПРЕДПРИЯТИЯ. Марка, встреченная
500 раз у одного завода, и марка у 40 заводов — разные вещи: для прогона по
площадкам ценна вторая, для карточки — обе.

Ничего не пишет в базы. Выход — три файла на дроп.

Запуск: python slovar_modeley.py [--min 1]
"""
import csv
import json
import os
import re
import sqlite3
import sys
import urllib.request
from collections import Counter, defaultdict

sys.path.insert(0, r'C:\seostat')
from app.services import centro_marki as CMK   # noqa: E402

ЦБ = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
ВЫХОД = 'SLOVAR-MODELEY-1s.csv'
ВЫХОД_НАШИ = 'SLOVAR-MODELEY-1s-NASHI-DLYA-PLOSHCHADOK.txt'
ВЫХОД_НЕОПОЗНАННЫЕ = 'SLOVAR-MODELEY-1s-NEOPOZNANNYE.csv'
# Порядок как в `po_faktam`: запятая режет марки, но не десятичную дробь.
_РЕЗ = re.compile(r'[|;/\n]|,(?!\d)')
_ХВОСТ = re.compile(
    r'\s*(?:ст\.?\s*№?\s*\d+|зав\.?\s*№?\s*\S+|инв\.?\s*№?\s*\S+|поз\.?\s*\S+'
    r'|техн\.?\s*№?\s*\S+|№\s*\d+)\s*$', re.I)


def канон(м):
    """Одна форма записи: «К 250 61 1», «К-250-61-1», «К250-61-1» — одно и то же."""
    м = _ХВОСТ.sub('', str(м or '').strip().strip('.,;:'))
    м = re.sub(r'\s+', ' ', м)
    if not re.match(r'^\d', м):
        м = re.sub(r'^([A-Za-zА-Яа-яЁё]{1,4})[\s]*(?=\d)', r'\1-', м)
    м = re.sub(r'(?<=\d)\.(?=\d)', ',', м)
    return м.upper()


def арг(имя, поум):
    try:
        return int(sys.argv[sys.argv.index(имя) + 1])
    except (ValueError, IndexError):
        return поум


def на_дроп(имя, данные):
    п = os.path.join(r'C:\sender\server', имя)
    with open(п, 'wb') as ф:
        ф.write(данные)
        ф.flush()
        os.fsync(ф.fileno())
    try:
        урл = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop')
        urllib.request.urlopen(urllib.request.Request(
            урл.rstrip('/') + '/' + имя, data=данные, method='PUT',
            headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}),
            timeout=300).read()
        return f'на дропе: {имя} ({len(данные)} байт)'
    except Exception as e:  # noqa: BLE001
        return f'{имя} не ушёл на дроп: {str(e)[:80]}'


def main():
    МИН = арг('--min', 1)
    цб = sqlite3.connect(f'file:{ЦБ}?mode=ro', uri=True, timeout=20)
    упоминаний = Counter()
    предприятий = defaultdict(set)
    сырых = Counter()
    строк = 0
    for инн, марка in цб.execute(
            "SELECT inn, COALESCE(model,'') FROM fact WHERE COALESCE(model,'')<>''"):
        строк += 1
        for кусок in _РЕЗ.split(str(марка)):
            к = канон(кусок)
            if len(к) < 3 or len(к) > 40:
                continue
            упоминаний[к] += 1
            предприятий[к].add(str(инн))
            сырых[к] = сырых.get(к, 0)
    цб.close()

    строки, наши, неопознанные = [], [], []
    итог = Counter()
    for м, n in упоминаний.most_common():
        if n < МИН:
            continue
        try:
            р = CMK.razobrat(м)
        except Exception:  # noqa: BLE001
            р = None
        if not р:
            неопознанные.append({'marka': м, 'upominaniy': n,
                                 'predpriyatiy': len(предприятий[м])})
            итог['не опознано справочником'] += 1
            continue
        тип = str(р.get('tip') or '')
        среда = str(р.get('sreda') or '')
        наш = bool(р.get('nash_profil'))
        итог['наша машина (центробежная воздушная)' if наш
             else f'опознано, но не наше: {классы(тип, среда)}'] += 1
        строки.append({
            'marka': м, 'upominaniy': n, 'predpriyatiy': len(предприятий[м]),
            'nash_profil': 'да' if наш else 'нет',
            'tip': тип[:120], 'sreda': среда[:60],
            'seriya': str(р.get('seriya') or '')[:60],
            'otkuda': str(р.get('otkuda') or '')[:60],
            'ssylka': str(р.get('ssylka') or '')[:200],
        })
        if наш:
            наши.append(м)

    print(json.dumps({
        'строк_фактов_с_маркой': строк,
        'РАЗНЫХ_МАРОК': len(упоминаний),
        'опознано_справочником': len(строки),
        'НАШИХ_МАРОК': len(наши),
        'не_опознано': len(неопознанные),
        'разбивка': итог.most_common(),
    }, ensure_ascii=False, indent=1))

    print('\nнаши марки, самые распространённые (марка — предприятий/упоминаний):')
    для_печати = sorted((с for с in строки if с['nash_profil'] == 'да'),
                        key=lambda с: -с['predpriyatiy'])[:20]
    for с in для_печати:
        print(f"  {с['marka']:20} {с['predpriyatiy']:4} / {с['upominaniy']:5}"
              f"  {с['tip'][:44]}")
    print('\nчаще всего НЕ опознано (кандидаты на разбор провайдером):')
    for с in sorted(неопознанные, key=lambda с: -с['predpriyatiy'])[:25]:
        print(f"  {с['marka']:24} {с['predpriyatiy']:4} / {с['upominaniy']:5}")

    вывод = []
    for имя, данные in (
            (ВЫХОД, csv_байты(строки)),
            (ВЫХОД_НЕОПОЗНАННЫЕ, csv_байты(неопознанные)),
            (ВЫХОД_НАШИ, ('\n'.join(sorted(наши)) + '\n').encode('utf-8'))):
        if данные:
            вывод.append(на_дроп(имя, данные))
    print('\n' + '\n'.join(вывод))


def классы(тип, среда):
    т = тип.lower()
    if re.search(r'\bгаз\b|газов', str(среда).lower()):
        return 'центробежная, но газовая'
    if 'поршнев' in т:
        return 'поршневая'
    if 'винтов' in т:
        return 'винтовая'
    if 'не определяется' in т or 'не названа' in str(среда).lower():
        return 'центробежная, среда не определена'
    return 'прочее'


def csv_байты(строки):
    if not строки:
        return b''
    import io
    б = io.StringIO()
    в = csv.DictWriter(б, fieldnames=list(строки[0]), delimiter=';',
                       lineterminator='\n')
    в.writeheader()
    в.writerows(строки)
    return b'\xef\xbb\xbf' + б.getvalue().encode('utf-8')


if __name__ == '__main__':
    main()
