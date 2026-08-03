# -*- coding: utf-8 -*-
"""Общий выбор целей для любого опа: по одному ИНН, по файлу, по всей панели.

ЗАЧЕМ. Владелец строит систему, где вбивается компания или ИНН и по ней
собирается всё, и при этом каждый модуль запускается отдельно по списку
компаний. Опись 164 модулей показала, что мешает: у 120 из них цели зашиты
константой внутри файла — `C:\\sender\\_ops\\sales_base.json` (555 предприятий
базы продажников) или `core396.json` (396 центробежных). То есть половина
конвейера ходит не по той выборке, по которой думает хозяин прогона.

Цена уже посчитана: протоколы закупочной комиссии и ЕИС со стороны поставщика
спрошены по 555 ИНН из 1573, ядро центробежных не спрашивалось ВОВСЕ; страница
«Руководство» и гриф УТВЕРЖДАЮ — по 555, потолок с флагом 951.

ЧЕТЫРЕ СПОСОБА ЗАДАТЬ ЦЕЛИ, в порядке приоритета:
    --inn 7712345678[,7798765432]   — одна компания или несколько через запятую
    --targets ПУТЬ                  — файл: txt, csv с колонкой inn, json, jsonl
    --iz-paneli [--vse]             — все предприятия панели обзвона; без --vse
                                      берутся только ВИДИМЫЕ, то есть без
                                      скрытых как мусор и непрофильные
    (ничего не задано)              — прежнее поведение опа, чтобы уже
                                      налаженные прогоны не сломались

ПОЧЕМУ УМОЛЧАНИЕ ОСТАЁТСЯ ПРЕЖНИМ. Сменить его молча значит незаметно
поменять смысл всех запусков, которые кто-то делает по памяти. Прежний список
остаётся, но теперь он ОДИН ИЗ, а не единственный, и оп печатает, откуда взял
цели — иначе снаружи не отличить «прогнали по всей базе» от «прогнали по
пятистам».

ПРОПУСК УЖЕ ПРОЙДЕННЫХ здесь же (`otsech_projdennye`): без него круги берут
одну и ту же голову списка. Ровно так стоял оп hh — каждый круг спрашивал
первые 200 из 1486, а 1286 не спрашивались ни разу, и прогон при этом
завершался успешно.
"""
import csv
import io
import json
import os
import re
import sqlite3
import sys

БАЗА_ПАНЕЛИ = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
БАЗА_ПРОДАЖ = os.getenv('CENTRO_SALES_DB') or r'C:\seostat\data\centro_sales.db'
СТАРЫЕ_СПИСКИ = (r'C:\sender\_ops\sales_base.json',
                 r'C:\sender\server\sales_base.json',
                 r'C:\sender\server\core396.json')


def _инн(значение):
    ц = re.sub(r'\D', '', str(значение or ''))
    return ц[:12] if len(ц) in (10, 12) else ''


def _арг(имя, argv):
    try:
        return argv[argv.index(имя) + 1]
    except (ValueError, IndexError):
        return ''


def из_файла(путь):
    """ИНН из файла любого из четырёх видов. Вид определяем по содержимому.

    По расширению определять нельзя: у нас на дропе лежат и `.csv` с
    разделителем «;», и `.json` со списком объектов, и `.jsonl`, и голые
    списки в `.txt`. Ошибка здесь тихая — вернётся пустой список, и прогон
    честно отработает по нулю целей, выглядя успешным.
    """
    if not os.path.exists(путь):
        raise SystemExit(f'файла целей нет: {путь}')
    сыр = open(путь, encoding='utf-8-sig', errors='replace').read().strip()
    если = []
    if сыр.startswith('['):
        try:
            for x in json.loads(сыр):
                если.append(_инн(x.get('inn') if isinstance(x, dict) else x))
        except Exception:  # noqa: BLE001
            если = []
    elif сыр.startswith('{'):
        try:
            д = json.loads(сыр)
            for з in д.values():
                if isinstance(з, list):
                    для = [_инн(x.get('inn') if isinstance(x, dict) else x)
                           for x in з]
                    если.extend(для)
        except Exception:  # noqa: BLE001
            если = []
    if not если and '\n' in сыр and сыр.lstrip().startswith('{'):
        for стр in сыр.splitlines():
            try:
                если.append(_инн(json.loads(стр).get('inn')))
            except Exception:  # noqa: BLE001
                continue
    if not если and (';' in сыр.split('\n', 1)[0] or ',' in сыр.split('\n', 1)[0]):
        for раздел in (';', ','):
            ряды = list(csv.DictReader(io.StringIO(сыр), delimiter=раздел))
            if ряды and len(ряды[0]) > 1:
                ключ = next((k for k in ряды[0] if (k or '').strip().lower()
                             in ('inn', 'инн')), None)
                if ключ:
                    если = [_инн(r.get(ключ)) for r in ряды]
                    break
    if не_пусто(если) is False:
        если = [_инн(с) for с in сыр.split()]
    итог, было = [], set()
    for и in если:
        if и and и not in было:
            было.add(и)
            итог.append(и)
    return итог


def не_пусто(сп):
    return bool([x for x in сп if x])


def из_paneli(только_видимые=True):
    """ИНН предприятий панели. По умолчанию — только видимые.

    Скрытые убраны как мусор, непрофильные или недоказанные; тратить на них
    прогон источника значит платить за то, что продавец всё равно не увидит.
    """
    if not os.path.exists(БАЗА_ПАНЕЛИ):
        raise SystemExit(f'базы панели нет: {БАЗА_ПАНЕЛИ}')
    cx = sqlite3.connect(f'file:{БАЗА_ПАНЕЛИ}?mode=ro', uri=True, timeout=20)
    все = [_инн(r[0]) for r in cx.execute('SELECT inn FROM company')]
    cx.close()
    все = [и for и in все if и]
    if not только_видимые or not os.path.exists(БАЗА_ПРОДАЖ):
        return все
    try:
        пр = sqlite3.connect(f'file:{БАЗА_ПРОДАЖ}?mode=ro', uri=True, timeout=20)
        скрыты = {_инн(r[0]) for r in пр.execute(
            "SELECT inn FROM hidden_item WHERE kind='company'")}
        пр.close()
    except Exception:  # noqa: BLE001
        скрыты = set()
    return [и for и in все if и not in скрыты]


def из_старого_списка():
    """Прежнее поведение: 555 предприятий базы продажников либо ядро 396."""
    итог, было = [], set()
    for путь in СТАРЫЕ_СПИСКИ:
        if not os.path.exists(путь):
            continue
        try:
            д = json.load(open(путь, encoding='utf-8'))
        except Exception:  # noqa: BLE001
            continue
        строки = []
        if isinstance(д, dict):
            for з in д.values():
                if isinstance(з, list):
                    строки.extend(з)
        elif isinstance(д, list):
            строки = д
        for x in строки:
            и = _инн(x.get('inn') if isinstance(x, dict) else x)
            if и and и not in было:
                было.add(и)
                итог.append(и)
        if итог:
            return итог, os.path.basename(путь)
    return итог, 'старый список не найден'


def отсечь_пройденные(цели, журнал, поле='inn', только_успешные=False):
    """Убрать уже пройденные по журналу прогона.

    `только_успешные=True` оставляет на повтор те, где была ошибка. По
    умолчанию НЕ повторяем ничего: «спросили и не нашли» — тоже ответ, и
    переспрашивать его каждый круг значит стоять на месте.
    """
    if not журнал or not os.path.exists(журнал):
        return цели, 0
    было = set()
    with open(журнал, encoding='utf-8', errors='replace') as ж:
        for стр in ж:
            try:
                з = json.loads(стр)
            except Exception:  # noqa: BLE001
                continue
            if только_успешные and з.get('err'):
                continue
            и = _инн(з.get(поле))
            if и:
                было.add(и)
    осталось = [и for и in цели if и not in было]
    return осталось, len(было)


def выбрать(argv=None, журнал='', лимит=0, печатать=True):
    """Главная точка входа. Возвращает (список_ИНН, откуда_взяли)."""
    argv = list(argv if argv is not None else sys.argv)
    один = _арг('--inn', argv)
    файл = _арг('--targets', argv)
    if один:
        цели = [и for и in (_инн(x) for x in one_split(один)) if и]
        откуда = f'аргумент --inn ({len(цели)})'
    elif файл:
        цели = из_файла(файл)
        откуда = f'файл {os.path.basename(файл)} ({len(цели)})'
    elif '--iz-paneli' in argv:
        цели = из_paneli(только_видимые='--vse' not in argv)
        откуда = ('панель обзвона, видимые' if '--vse' not in argv
                  else 'панель обзвона, все') + f' ({len(цели)})'
    else:
        цели, имя = из_старого_списка()
        откуда = f'прежний список {имя} ({len(цели)})'
    было = 0
    if журнал:
        цели, было = отсечь_пройденные(цели, журнал)
    if лимит:
        цели = цели[:лимит]
    if печатать:
        print(f'цели: {откуда}; пройдено ранее {было}; в этот прогон {len(цели)}')
        sys.stdout.flush()
    return цели, откуда


def one_split(значение):
    return re.split(r'[,\s;]+', str(значение or '').strip())
