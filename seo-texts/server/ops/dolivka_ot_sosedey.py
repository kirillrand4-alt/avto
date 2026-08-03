# -*- coding: utf-8 -*-
"""Долить в панель обзвона людей и номера из файлов второй и третьей сессий.

Пункт 14 владельца: «заливаем все данные в панель для продажников,
перепроверяем друг за другом и вливаем». Свои данные я влил (`dolit_v_panel`),
файлы соседей на дропе лежали и продавцу не показывались. Замер по базе панели:

  VOZDUSHNYE-CENTROBEZHNIKI-s-LPR.csv  445 человек, которых в панели нет
  OBHOD-kontakty-3s.csv                102 человека и контакты с видом
  BEZ-TEHLPR-1486-dadata.csv           руководители по ЕГРЮЛ

КОЛОНКИ У ТРЁХ СЕССИЙ РАЗНЫЕ, и это не мелочь: `csv.DictReader` на неверном
имени ключа молча отдаёт None. Мой первый замер искал человека в `person/fio`,
а у третьей сессии он в `rukovoditel` — вышло «людей 0», и это выглядело как
факт о файле, хотя было фактом о моей карте колонок. Поэтому карта здесь
задана явно по каждому файлу, а не угадывается.

ЧЕГО НЕ ДЕЛАЕМ. Мёртвые юрлица (LIQUIDATED, BANKRUPT) из файла ЕГРЮЛ не
вливаем: владелец просил базу без мусора, а звонок ликвидированному заводу —
это и есть мусор. Число пропущенных печатаем, чтобы решение было видно.

ОДИН НОМЕР НА МНОГИХ ЛЮДЕЙ — номер здания, а не личный. Если в файле один и тот
же номер стоит у трёх и более человек, он пишется БЕЗ имени и роли: иначе
продавец звонит «Иванову» на общий заводской телефон. Ловушку поймали на своей
же выгрузке, где один номер разошёлся по восьми людям.

Скрытые предприятия НЕ пропускаем. Скрытие — решение продавца на витрине и
обратимо; если завод вернут, данные должны быть на месте, а не «мы их тогда не
влили».

Пишем в базу И файлом на дроп: пересборка `centrifugal.db` заменяет базу
целиком, и всё, что легло только в неё, исчезнет.

По умолчанию СУХОЙ ПРОГОН. Запуск: python dolivka_ot_sosedey.py [--apply]
"""
import csv
import io
import os
import re
import shutil
import sqlite3
import sys
import time
import urllib.request
from collections import Counter, defaultdict

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

ПРИМЕНИТЬ = '--apply' in sys.argv
ДРОП = r'C:\seostat\drop\drop-storage'
БАЗА = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
ИМЯ_ВЫГРУЗКИ = 'DOLIVKA-ot-sosedey-v-panel.csv'
_ДОБ = re.compile(r'\s*(?:доб|вн|внутр|ext)\.?\s*[:№]?\s*[\d\-]+\s*$', re.I)
_МЁРТВЫЕ = ('LIQUIDAT', 'BANKRUPT', 'ЛИКВИДИР', 'БАНКРОТ')


def клч(т):
    return re.sub(r'\s+', ' ', str(т or '').strip().lower()).replace('ё', 'е')


def д10(т):
    ц = re.sub(r'\D', '', _ДОБ.sub('', str(т or '')))
    return ц[-10:] if len(ц) >= 10 else ''


def вид(ц):
    return 'нет номера' if not ц else ('мобильный' if ц.startswith('9')
                                       else 'городской')


def инн_кл(т):
    return re.sub(r'\D', '', str(т or ''))[:12]


def читать(имя):
    п = os.path.join(ДРОП, имя)
    if not os.path.exists(п):
        print(f'  НЕТ файла {имя} — пропускаю')
        return []
    csv.field_size_limit(10 ** 7)
    сыр = open(п, encoding='utf-8-sig', errors='replace').read()
    ряды = list(csv.DictReader(io.StringIO(сыр), delimiter=';'))
    if ряды and len(ряды[0]) <= 1:
        ряды = list(csv.DictReader(io.StringIO(сыр), delimiter=','))
    return ряды


def на_дроп(путь, имя):
    урл = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop')
    зпр = urllib.request.Request(
        урл.rstrip('/') + '/' + имя, data=open(путь, 'rb').read(), method='PUT',
        headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
    with urllib.request.urlopen(зпр, timeout=600) as о:
        return о.read()[:120]


def человек_ли(т):
    """Имя человека, а не организация и не номер.

    В поле человека у нас уже приезжали управляющие компании из ЕГРЮЛ (165
    строк вида «директор ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ…») и голые
    телефоны из объединённых колонок. И то и другое продавцу бесполезно.
    """
    т = (т or '').strip()
    if len(т) < 4:
        return False
    if re.fullmatch(r'[\d\s()+\-]{4,}', т):
        return False
    if re.search(r'\b(ООО|ОАО|ЗАО|АО|ПАО|МУП|ГУП|ФГУП|УК)\b|общество|'
                 r'предприяти|учреждени|компани|организаци|акционерн|унитарн',
                 т, re.I):
        return False
    return True


def main():
    тех = set(EDB.EnrichDB.TECH_ROLES) | {'техконтакт'}
    цб = sqlite3.connect(f'file:{БАЗА}?mode=ro', uri=True, timeout=15)
    инн_панели = {инн_кл(r[0]) for r in цб.execute('SELECT DISTINCT inn FROM company')}
    есть_люди = {(инн_кл(и), клч(п)) for и, п in
                 цб.execute('SELECT inn, person FROM person') if п}
    есть_тел = set()
    for и, з in цб.execute("SELECT inn, value FROM contact WHERE kind='phone'"):
        ц = д10(з)
        if ц:
            есть_тел.add((инн_кл(и), ц))
    цб.close()
    print(f'в панели: предприятий {len(инн_панели)}, людей {len(есть_люди)}, '
          f'телефонов {len(есть_тел)}')

    нов_люди, нов_тел = [], []
    видел_л, видел_т = set(есть_люди), set(есть_тел)
    отчёт = Counter()

    # ---- 1. вторая сессия: люди с ролью и личным номером
    ряды = читать('VOZDUSHNYE-CENTROBEZHNIKI-s-LPR.csv')
    общие = defaultdict(set)          # номер -> сколько разных людей на нём
    for r in ряды:
        ц = д10(r.get('lichnyy_nomer'))
        if ц and человек_ли(r.get('chelovek')):
            общие[ц].add(клч(r.get('chelovek')))
    for r in ряды:
        и = инн_кл(r.get('inn'))
        чел = (r.get('chelovek') or '').strip()
        if и not in инн_панели or not человек_ли(чел):
            continue
        к = (и, клч(чел))
        if к in видел_л:
            отчёт['2с: человек уже в панели'] += 1
            continue
        видел_л.add(к)
        роль = (r.get('rol') or '').strip()
        ц = д10(r.get('lichnyy_nomer'))
        личный = ц and len(общие.get(ц, ())) < 3
        if ц and not личный:
            отчёт['2с: номер общий (3+ человека), человек без номера'] += 1
        нов_люди.append((
            и, чел, (r.get('dolzhnost') or '')[:120],
            роль or 'роль не установлена',
            ('+7' + ц) if личный else None,
            вид(ц) if личный else 'нет номера',
            None, (r.get('ssylka_na_cheloveka') or None),
            (r.get('istochnik_cheloveka') or 'вторая сессия')[:120],
            1 if роль in тех else 0))
        отчёт['2с: людей влито'] += 1

    # ---- 2. третья сессия: контакты с обхода сайтов, у части есть человек
    for r in читать('OBHOD-kontakty-3s.csv'):
        и = инн_кл(r.get('inn'))
        if и not in инн_панели:
            continue
        значение = (r.get('kontakt') or '').strip()
        чел = (r.get('chelovek') or '').strip()
        вид_к = (r.get('vid') or '').strip()
        если_человек = человек_ли(чел)
        if (r.get('tip') or '').strip() == 'телефон' or д10(значение):
            ц = д10(значение)
            if not ц or (и, ц) in видел_т:
                отчёт['3с обход: номер уже в панели'] += 1
                continue
            видел_т.add((и, ц))
            нов_тел.append((
                и, значение, 'phone', чел if если_человек else None,
                вид_к or None, None, вид(ц),
                (r.get('istochnik') or 'обход сайта (3-я сессия)')[:120],
                (r.get('ssylka') or None), 0, 0,
                1 if (если_человек or вид_к) else 0,
                0 if если_человек else 1))
            отчёт['3с обход: номеров влито'] += 1
        if если_человек:
            к = (и, клч(чел))
            if к in видел_л:
                continue
            видел_л.add(к)
            нов_люди.append((
                и, чел, вид_к[:120], 'роль не установлена',
                значение if д10(значение) else None,
                вид(д10(значение)), None, (r.get('ssylka') or None),
                (r.get('istochnik') or 'обход сайта (3-я сессия)')[:120], 0))
            отчёт['3с обход: людей влито'] += 1

    # ---- 3. третья сессия: руководители по ЕГРЮЛ
    for r in читать('BEZ-TEHLPR-1486-dadata.csv'):
        и = инн_кл(r.get('inn'))
        if и not in инн_панели:
            continue
        статус = (r.get('status') or '').upper()
        if any(м in статус for м in _МЁРТВЫЕ):
            отчёт['ЕГРЮЛ: мёртвое юрлицо, пропущено'] += 1
            continue
        рук = (r.get('rukovoditel') or '').strip()
        if человек_ли(рук):
            к = (и, клч(рук))
            if к not in видел_л:
                видел_л.add(к)
                нов_люди.append((
                    и, рук, (r.get('dolzhnost_rukovoditelya') or '')[:120],
                    'руководитель', None, 'нет номера', None, None,
                    'ЕГРЮЛ (3-я сессия)', 0))
                отчёт['ЕГРЮЛ: руководителей влито'] += 1
        for т in re.split(r'[|;,]', r.get('obzvon_telefony') or ''):
            ц = д10(т)
            if not ц or (и, ц) in видел_т:
                continue
            видел_т.add((и, ц))
            нов_тел.append((и, т.strip(), 'phone', None, None, None, вид(ц),
                            'ЕГРЮЛ (3-я сессия)', None, 0, 0, 0, 1))
            отчёт['ЕГРЮЛ: номеров влито'] += 1

    print(f'НОВОГО ДЛЯ ПАНЕЛИ: людей {len(нов_люди)}, номеров {len(нов_тел)}')
    for к, v in отчёт.most_common():
        print(f'   {к}: {v}')
    for с in нов_люди[:5]:
        print(f'  человек: {с[0]} {с[1][:26]:<26} {с[3][:16]:<16} {с[4] or "без номера"}')

    if not ПРИМЕНИТЬ:
        print('\nсухой прогон. Повторить с --apply')
        return
    if not (нов_люди or нов_тел):
        print('доливать нечего')
        return

    коп = БАЗА + '.bak-' + str(int(time.time()))
    shutil.copy2(БАЗА, коп)
    print(f'копия базы: {os.path.basename(коп)}')
    cx = sqlite3.connect(БАЗА, timeout=30)
    try:
        cx.executemany(
            'INSERT INTO person (inn, person, position, role, phone, '
            'phone_type, email, source_url, source, is_tech) '
            'VALUES (?,?,?,?,?,?,?,?,?,?)', нов_люди)
        cx.executemany(
            'INSERT INTO contact (inn, value, kind, person, role, position, '
            'phone_type, source, source_url, is_purchaser, is_tech, has_role, '
            'is_unknown_owner) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)', нов_тел)
        cx.execute("INSERT OR REPLACE INTO import_info (key, value) "
                   "VALUES ('dolito_ot_sosedey', ?)",
                   (time.strftime('%Y-%m-%dT%H:%M:%S'),))
        cx.commit()
    finally:
        cx.close()

    # ---- числа ПЕРЕЧИТЫВАНИЕМ базы, а не по длине списков
    cx = sqlite3.connect(f'file:{БАЗА}?mode=ro', uri=True, timeout=15)
    л = cx.execute('SELECT COUNT(*) FROM person').fetchone()[0]
    тх = cx.execute('SELECT COUNT(*) FROM person WHERE is_tech=1').fetchone()[0]
    т = cx.execute("SELECT COUNT(*) FROM contact WHERE kind='phone'").fetchone()[0]
    cx.close()
    print('\n=== ИЗ БАЗЫ ПАНЕЛИ ПОСЛЕ ДОЛИВКИ ===')
    print(f'  людей {л}, из них технических {тх}, телефонов {т}')

    # ---- и файлом, иначе пересборка базы это сотрёт
    п = os.path.join(r'C:\sender\server', ИМЯ_ВЫГРУЗКИ)
    with open(п, 'w', encoding='utf-8-sig', newline='') as ф:
        в = csv.writer(ф, delimiter=';')
        в.writerow(['tip', 'inn', 'fio_ili_nomer', 'dolzhnost', 'rol',
                    'telefon', 'istochnik', 'ssylka', 'tehLPR'])
        for с in нов_люди:
            в.writerow(['человек', с[0], с[1], с[2], с[3], с[4] or '',
                        с[8], с[7] or '', 'да' if с[9] else 'нет'])
        for с in нов_тел:
            в.writerow(['номер', с[0], с[1], с[5] or '', с[4] or '', с[1],
                        с[7], с[8] or '', 'нет'])
    print(f'файл {ИМЯ_ВЫГРУЗКИ}: {os.path.getsize(п)} байт → дроп: '
          f'{на_дроп(п, ИМЯ_ВЫГРУЗКИ)!r}')


if __name__ == '__main__':
    main()
