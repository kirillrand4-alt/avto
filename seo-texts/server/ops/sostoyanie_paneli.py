# -*- coding: utf-8 -*-
"""Что панель показывает СЕЙЧАС и что добавят файлы соседей — до пересборки.

Пересборка `centrifugal.db` заменяет базу ЦЕЛИКОМ. Всё, что доливалось в неё
напрямую (а я доливал — `DOLIVKA-v-panel-ot-1-sessii.csv` лёг прямо в базу,
минуя сборщик), исчезнет, если не попадёт во входные CSV. Поэтому сначала
цифры, потом сборка: иначе «обновил панель» может означать «уронил панель с
4540 человек до 1566» и выглядеть при этом успешно.

Считаем три вещи:
  1. что в базе панели сейчас — предприятия, факты, люди, телефоны, дата сборки;
  2. что нового принесут файлы на дропе — людей и номеров, которых в панели НЕТ
     (сверка по ключам ИНН+имя и ИНН+десять цифр, а не по общему счёту: счёт
     может сойтись при полностью разном составе);
  3. чего в файлах НЕТ из того, что в панели уже есть — то есть что пересборка
     потеряет, если собрать только по ним.

Голый sqlite3 без `app.services`: раннер запускает питоном рассыльщика, где нет
bcrypt, и импорт сервисов панели падает до первой полезной строки.

Запуск: python sostoyanie_paneli.py
"""
import csv
import io
import json
import os
import re
import sqlite3

ДРОП = r'C:\seostat\drop\drop-storage'
БАЗА = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
_ДОБ = re.compile(r'\s*(?:доб|вн|внутр|ext)\.?\s*[:№]?\s*[\d\-]+\s*$', re.I)
_ТЕЛ = re.compile(r'(?:\+?7|8)?[\s(\-]*\d{3,5}[\s)\-]*\d[\d\s\-]{5,10}\d')

ФАЙЛЫ = ('DOLIVKA-v-panel-ot-1-sessii.csv',
         'BAZA-CENTROBEZHNIKI-OBSHCHAYA.csv',
         'TEHLPR-VSE-s-provenansom.csv',
         'VOZDUSHNYE-CENTROBEZHNIKI-s-LPR.csv',
         'OBHOD-kontakty-3s.csv',
         'BEZ-TEHLPR-1486-dadata.csv')


def д10(т):
    ц = re.sub(r'\D', '', _ДОБ.sub('', str(т or '')))
    return ц[-10:] if len(ц) >= 10 else ''


def клч(т):
    return re.sub(r'\s+', ' ', str(т or '').strip().lower()).replace('ё', 'е')


def инн(т):
    return re.sub(r'\D', '', str(т or ''))[:12]


def читать(имя):
    п = os.path.join(ДРОП, имя)
    if not os.path.exists(п):
        return None
    csv.field_size_limit(10 ** 7)
    сыр = open(п, encoding='utf-8-sig', errors='replace').read()
    ряды = list(csv.DictReader(io.StringIO(сыр), delimiter=';'))
    if ряды and len(ряды[0]) <= 1:
        ряды = list(csv.DictReader(io.StringIO(сыр), delimiter=','))
    return ряды


def поле(r, *варианты):
    """Значение по первому подошедшему имени колонки.

    Имена колонок у трёх сессий разные, а `DictReader` на отсутствующем ключе
    молча отдаёт None — то есть неверно угаданное имя даёт не ошибку, а тихий
    ноль. Поэтому перебираем варианты и подстроку.
    """
    for в in варианты:
        if r.get(в):
            return r[в]
    for k, v in r.items():
        if v and any(в in (k or '').lower() for в in варианты):
            return v
    return ''


def main():
    cx = sqlite3.connect(f'file:{БАЗА}?mode=ro', uri=True, timeout=10)
    таблицы = {r[0] for r in cx.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    итог = {'база_панели': БАЗА, 'таблицы': sorted(таблицы)}
    for т in ('company', 'fact', 'person', 'people', 'phone', 'news'):
        if т in таблицы:
            итог[f'строк_{т}'] = cx.execute(
                f'SELECT COUNT(*) FROM "{т}"').fetchone()[0]
    if 'import_info' in таблицы:
        кур = cx.execute('SELECT * FROM import_info')
        имена = [c[0] for c in кур.description]
        итог['import_info'] = [dict(zip(имена, r)) for r in кур.fetchall()]

    # ключи панели: люди (ИНН+имя) и номера (ИНН+10 цифр)
    таб_людей = 'person' if 'person' in таблицы else (
        'people' if 'people' in таблицы else '')
    люди_п, тел_п, инн_п = set(), set(), set()
    if 'company' in таблицы:
        инн_п = {инн(r[0]) for r in cx.execute('SELECT inn FROM company')}
    if таб_людей:
        колонки = {c[1] for c in cx.execute(f'PRAGMA table_info("{таб_людей}")')}
        имя_к = ('name' if 'name' in колонки else
                 'person' if 'person' in колонки else
                 'fio' if 'fio' in колонки else '')
        if имя_к:
            for и, н in cx.execute(f'SELECT inn, "{имя_к}" FROM "{таб_людей}"'):
                люди_п.add((инн(и), клч(н)))
    # Таблица номеров называется `contact`, а не `phone`. Первый прогон искал
    # `phone`, не нашёл и честно показал 0 ключей — а дальше КАЖДЫЙ номер из
    # файлов выглядел новым. Ноль в знаменателе не спорит: он делает любой
    # источник «полностью новым» и выглядит как отличная новость.
    итог['схема'] = {т: [c[1] for c in cx.execute(f'PRAGMA table_info("{т}")')]
                     for т in таблицы if not т.startswith('sqlite_')}
    if 'contact' in таблицы:
        колонки = [c[1] for c in cx.execute('PRAGMA table_info("contact")')]
        тк = next((k for k in ('phone', 'number', 'value', 'contact', 'kontakt')
                   if k in колонки), '')
        if тк:
            for и, т in cx.execute(f'SELECT inn, "{тк}" FROM contact'):
                ц = д10(т)
                if ц:
                    тел_п.add((инн(и), ц))
    итог['в_панели_людей_ключей'] = len(люди_п)
    итог['в_панели_номеров_ключей'] = len(тел_п)

    по_файлам = {}
    for имя in ФАЙЛЫ:
        ряды = читать(имя)
        if ряды is None:
            по_файлам[имя] = 'НЕТ на дропе'
            continue
        нов_л = нов_т = нов_к = 0
        всего_л = всего_т = 0
        for r in ряды:
            и = инн(поле(r, 'inn', 'инн'))
            if not и:
                continue
            if и not in инн_п:
                нов_к += 1
            # В DOLIVKA колонка одна на человека И на номер (`fio_ili_nomer`),
            # различает их `tip`. Без этой развилки все 5490 строк считались
            # людьми, и «людей нет в панели: 2875» было цифрой про телефоны.
            ч = клч(поле(r, 'person', 'fio', 'chelovek', 'имя', 'человек'))
            if re.fullmatch(r'[\d\s()+\-]{6,}', ч or ''):
                ч = ''
            if ч and len(ч) > 3:
                всего_л += 1
                if (и, ч) not in люди_п:
                    нов_л += 1
            for m in _ТЕЛ.finditer(' '.join(
                    str(v) for k, v in r.items()
                    if v and re.search(r'phone|tel|номер|телеф', k or '', re.I))):
                ц = д10(m.group(0))
                if not ц:
                    continue
                всего_т += 1
                if (и, ц) not in тел_п:
                    нов_т += 1
        по_файлам[имя] = {
            'строк': len(ряды),
            'людей_в_файле': всего_л, 'из_них_НЕТ_в_панели': нов_л,
            'номеров_в_файле': всего_т, 'номеров_нет_в_панели': нов_т,
            'строк_по_предприятиям_вне_панели': нов_к,
            'колонки': list(ряды[0].keys())[:14] if ряды else [],
        }
    итог['файлы'] = по_файлам
    # Раннер отдаёт ПОСЛЕДНИЕ 6000 символов stdout. Развёрнутый json.dumps с
    # indent отрезался с ГОЛОВЫ, то есть терялись как раз счётчики базы —
    # а выглядело это как «скрипт напечатал середину». Печатаем плотно.
    print('ПАНЕЛЬ:', json.dumps(
        {k: v for k, v in итог.items()
         if k not in ('файлы', 'схема', 'import_info', 'таблицы')},
        ensure_ascii=False))
    print('СХЕМА contact:', итог.get('схема', {}).get('contact'))
    print('СХЕМА person :', итог.get('схема', {}).get('person'))
    print('СБОРКА:', json.dumps(
        {r['key']: r['value'] for r in итог.get('import_info', [])
         if not r['key'].endswith('sha256')}, ensure_ascii=False))
    for имя, v in по_файлам.items():
        if isinstance(v, str):
            print(f'{имя}: {v}')
            continue
        print(f"{имя}: строк {v['строк']}, людей {v['людей_в_файле']} "
              f"(нет в панели {v['из_них_НЕТ_в_панели']}), номеров "
              f"{v['номеров_в_файле']} (нет в панели {v['номеров_нет_в_панели']}), "
              f"строк по предприятиям вне панели {v['строк_по_предприятиям_вне_панели']}")


if __name__ == '__main__':
    main()
