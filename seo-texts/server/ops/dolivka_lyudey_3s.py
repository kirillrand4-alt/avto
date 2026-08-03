# -*- coding: utf-8 -*-
"""Долить в панель людей из свода обзвона 3-й сессии.

ЧТО ЗА ФАЙЛ. `VAZHNOE-3s-SPISOK-OBZVONA-POLNYY.csv`: 8 254 строки по 507
предприятиям, сведённые из девяти источников с накопительным провенансом —
один человек, найденный трижды, идёт одной строкой с числом источников 3.
Колонка `vid` говорит, что именно взято: личный мобильный, прямой номер,
приёмная, отдел, именная почта. Колонка `prioritet` уже отсортирована.

ГЛАВНАЯ ОГОВОРКА САМОЙ 3-Й СЕССИИ, И ОНА ЗДЕСЬ РЕШАЮЩАЯ: 3 971 строка это
«ФИО из патента, контакта нет — имя для поиска номера». Привязка человека к
предприятию там доказана только тем, что имя предприятия встретилось в тексте
патента. Это не контакты, а цели поиска, и в панель они идти НЕ ДОЛЖНЫ:
продавец увидит фамилию с ролью «главный инженер» и решит, что это его
человек. Поэтому льём только строки С КОНТАКТОМ, а патентные имена без
контакта считаем и откладываем файлом.

ВТОРАЯ ЗАЩИТА — ОТ ОРГАНИЗАЦИИ В ПОЛЕ ЧЕЛОВЕКА. У нас уже приезжали
управляющие компании из ЕГРЮЛ («директор ОБЩЕСТВО С ОГРАНИЧЕННОЙ…») и голые
телефоны в колонке ФИО. Проверка `человек_ли` та же, что в доливке от соседей.

Дедуп по (ИНН, нормализованное ФИО) и по (ИНН, десять цифр номера).

По умолчанию СУХОЙ ПРОГОН. Запуск: python dolivka_lyudey_3s.py [--apply]
"""
import csv
import json
import os
import re
import shutil
import sqlite3
import sys
import time
import urllib.request
from collections import Counter

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

БАЗА = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
ДРОП = r'C:\seostat\drop\drop-storage'
ФАЙЛ = 'VAZHNOE-3s-SPISOK-OBZVONA-POLNYY.csv'
ОТЛОЖ = 'OTLOZHENO-patentnye-imena-bez-kontakta.csv'
ПРИМЕНИТЬ = '--apply' in sys.argv
_ДОБ = re.compile(r'\s*(?:доб|вн|внутр|ext)\.?\s*[:№]?\s*[\d\-]+\s*$', re.I)
# Строка, у которой источник только патент: связь с предприятием не доказана.
_ТОЛЬКО_ПАТЕНТ = re.compile(r'^\s*патент', re.I)


def инн_кл(т):
    return re.sub(r'\D', '', str(т or ''))[:12]


def клч(т):
    return re.sub(r'\s+', ' ', str(т or '').strip().lower()).replace('ё', 'е')


def д10(т):
    ц = re.sub(r'\D', '', _ДОБ.sub('', str(т or '')))
    return ц[-10:] if len(ц) >= 10 else ''


def вид_номера(ц):
    return 'нет номера' if not ц else ('мобильный' if ц.startswith('9')
                                       else 'городской')


# ЯРЛЫК, УЕХАВШИЙ В ФАМИЛИЮ. Сухой прогон показал двоих: «Телефон Милош
# Крестович» и «Начальник Денис Юрьевич». Это не люди, а результат разбора, где
# подпись поля прилипла к имени: в документе стояло «Телефон: Милош…» и
# «Начальник отдела Денис Юрьевич…». Отчество на месте, фамилия — слово-ярлык,
# и обе строки выглядят как настоящий контакт. Продавец позвонит и спросит
# «Телефона Милоша Крестовича».
_ЯРЛЫК_В_ФИО = re.compile(
    r'^\s*(?:телефон|тел|факс|почта|e-?mail|контакт\w*|приёмн\w*|приемн\w*|'
    r'начальник\w*|директор\w*|руководител\w*|менеджер\w*|специалист\w*|'
    r'инженер\w*|отдел\w*|бухгалтер\w*|секретар\w*|диспетчер\w*|мастер|'
    r'зам|заместител\w*|ответственн\w*|исполнител\w*)\b', re.I)


def человек_ли(т):
    """Имя человека, а не организация, не номер и не подпись поля."""
    т = (т or '').strip()
    if len(т) < 4:
        return False
    if re.fullmatch(r'[\d\s()+\-]{4,}', т):
        return False
    if re.search(r'\b(ООО|ОАО|ЗАО|АО|ПАО|МУП|ГУП|ФГУП|УК)\b|общество|'
                 r'предприяти|учреждени|компани|организаци|акционерн|унитарн',
                 т, re.I):
        return False
    if _ЯРЛЫК_В_ФИО.match(т):
        return False
    return True


def номер_живой(ц):
    """Не заглушка. `0000000000` и `9999999999` приезжают из полей-пустышек."""
    return bool(ц) and len(set(ц)) > 2


def main():
    csv.field_size_limit(10 ** 7)
    путь = os.path.join(ДРОП, ФАЙЛ)
    if not os.path.exists(путь):
        raise SystemExit(f'нет {ФАЙЛ} на дропе сервера')
    тех = set(EDB.EnrichDB.TECH_ROLES) | {'техконтакт'}

    цб = sqlite3.connect(f'file:{БАЗА}?mode=ro', uri=True, timeout=20)
    инн_панели = {инн_кл(r[0]) for r in цб.execute('SELECT DISTINCT inn FROM company')}
    есть_люди = {(инн_кл(и), клч(п)) for и, п in
                 цб.execute('SELECT inn, person FROM person') if п}
    есть_тел = set()
    for и, з in цб.execute("SELECT inn, value FROM contact WHERE kind='phone'"):
        ц = д10(з)
        if ц:
            есть_тел.add((инн_кл(и), ц))
    было_людей, было_тел = len(есть_люди), len(есть_тел)
    цб.close()
    print(f'в панели: предприятий {len(инн_панели)}, разных людей {было_людей}, '
          f'разных номеров {было_тел}')

    нов_люди, нов_тел, отложено = [], [], []
    отсев = Counter()
    виды = Counter()
    предпр = set()
    прочитано = 0
    with open(путь, encoding='utf-8-sig', errors='replace', newline='') as ф:
        for r in csv.DictReader(ф, delimiter=';'):
            прочитано += 1
            и = инн_кл(r.get('inn'))
            фио = (r.get('fio') or '').strip()
            контакт = (r.get('kontakt') or '').strip()
            вид = (r.get('vid') or '').strip()
            тип_к = (r.get('tip_kontakta') or '').strip()
            ист = (r.get('istochniki') or '').strip()
            if и not in инн_панели:
                отсев['предприятия нет в панели'] += 1
                continue
            if not контакт:
                # Патентное имя без контакта: связь с предприятием доказана
                # только упоминанием. В панель не пускаем, но и не теряем.
                отсев['имя без контакта (цель поиска, не контакт)'] += 1
                отложено.append((и, фио, (r.get('dolzhnost') or '')[:100],
                                 (r.get('rol') or ''), ист[:120]))
                continue
            if фио and not человек_ли(фио):
                отсев['в поле человека организация или номер'] += 1
                continue
            if not фио and _ТОЛЬКО_ПАТЕНТ.search(ист):
                отсев['патентная строка без имени'] += 1
                continue

            роль = (r.get('rol') or '').strip()
            должность = (r.get('dolzhnost') or '').strip()
            ссылка = (r.get('ssylka') or '').strip()
            техн = 1 if роль in тех else 0
            ц = д10(контакт) if тип_к != 'почта' else ''
            if ц and not номер_живой(ц):
                отсев['номер-заглушка вида 0000000000'] += 1
                ц = ''
                if тип_к != 'почта':
                    continue
            почта = контакт if тип_к == 'почта' else ''

            if фио:
                к = (и, клч(фио))
                if к not in есть_люди:
                    есть_люди.add(к)
                    предпр.add(и)
                    виды[вид or 'вид не указан'] += 1
                    нов_люди.append((
                        и, фио, должность[:120], роль or 'роль не установлена',
                        (contact_or_none(контакт) if тип_к != 'почта' else None),
                        вид_номера(ц), почта or None, ссылка or None,
                        (ист or 'свод 3-й сессии')[:120], техн))
            if ц and (и, ц) not in есть_тел:
                есть_тел.add((и, ц))
                предпр.add(и)
                нов_тел.append((
                    и, контакт[:60], 'phone', фио or None, роль or None,
                    должность[:120] or None, вид_номера(ц),
                    (ист or 'свод 3-й сессии')[:120], ссылка or None,
                    1 if роль in ('снабжение/закупки', 'снабжение') else 0,
                    техн, 1 if (фио or роль) else 0, 0 if фио else 1))

    print(json.dumps({
        'строк_прочитано': прочитано,
        'НОВЫХ_людей': len(нов_люди),
        'из_них_технических': sum(1 for с in нов_люди if с[9]),
        'НОВЫХ_номеров': len(нов_тел),
        'из_них_личных_мобильных': sum(1 for с in нов_тел if с[6] == 'мобильный'),
        'предприятий_затронуто': len(предпр),
        'что_за_люди_по_виду_контакта': виды.most_common(8),
        'отсеяно': отсев.most_common(8),
        'отложено_имён_без_контакта': len(отложено),
        'режим': 'ПРИМЕНЕНИЕ' if ПРИМЕНИТЬ else 'сухой (--apply)',
    }, ensure_ascii=False, indent=1))
    for с in нов_люди[:8]:
        print(f'  {с[0]}  {с[1][:30]:<30} {с[3][:18]:<18} {с[4] or с[6]}')

    if отложено:
        выложить(ОТЛОЖ, ['inn', 'fio', 'dolzhnost', 'rol', 'istochniki'],
                 отложено)

    if not ПРИМЕНИТЬ or not (нов_люди or нов_тел):
        if not ПРИМЕНИТЬ:
            print('\nсухой прогон. Повторить с --apply')
        return

    коп = БАЗА + '.bak-' + str(int(time.time()))
    shutil.copy2(БАЗА, коп)
    print(f'копия базы: {os.path.basename(коп)}')
    cx = sqlite3.connect(БАЗА, timeout=60)
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
                   "VALUES ('dolito_lyudey_3s_1_sessiey', ?)",
                   (time.strftime('%Y-%m-%dT%H:%M:%S'),))
        cx.commit()
    finally:
        cx.close()

    # ЧИСЛА В ТЕХ ЖЕ ЕДИНИЦАХ, ЧТО И ДО ДОЛИВКИ: пары, а не строки таблицы.
    цб = sqlite3.connect(f'file:{БАЗА}?mode=ro', uri=True, timeout=20)
    пары_л = len({(инн_кл(и), клч(п)) for и, п in
                  цб.execute('SELECT inn, person FROM person') if п})
    пары_т = len({(инн_кл(и), д10(з)) for и, з in
                  цб.execute("SELECT inn, value FROM contact WHERE kind='phone'")
                  if д10(з)})
    тех_л = цб.execute(
        'SELECT COUNT(*) FROM person WHERE is_tech=1').fetchone()[0]
    цб.close()
    print(json.dumps({
        'разных_людей_было': было_людей, 'стало': пары_л,
        'разных_номеров_было': было_тел, 'стало_номеров': пары_т,
        'строк_технических_людей': тех_л,
    }, ensure_ascii=False))

    выложить('DOLIVKA-lyudey-3s-ot-1-sessii.csv',
             ['inn', 'fio', 'dolzhnost', 'rol', 'telefon', 'vid', 'pochta',
              'ssylka', 'istochnik', 'tehLPR'], нов_люди)


def contact_or_none(з):
    return з or None


def выложить(имя, шапка, ряды):
    """Файл рядом с базой и на дроп: доливка должна пережить пересборку."""
    п = os.path.join(r'C:\sender\server', имя)
    with open(п, 'w', encoding='utf-8-sig', newline='') as ф:
        в = csv.writer(ф, delimiter=';')
        в.writerow(шапка)
        for с in ряды:
            в.writerow(list(с)[:len(шапка)])
    try:
        урл = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop')
        urllib.request.urlopen(urllib.request.Request(
            урл.rstrip('/') + '/' + имя, data=open(п, 'rb').read(),
            method='PUT',
            headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}),
            timeout=300).read()
        print(f'на дропе: {имя} ({len(ряды)} строк)')
    except Exception as e:  # noqa: BLE001
        print(f'{имя} записан локально, на дроп не ушёл: {e}')


if __name__ == '__main__':
    main()
