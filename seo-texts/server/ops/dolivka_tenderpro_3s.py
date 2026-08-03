# -*- coding: utf-8 -*-
"""Люди из карточек Тендер.Про (сбор 3-й сессии) — с восстановлением ИНН.

ЗАЧЕМ ОТДЕЛЬНЫЙ ОП. Третья сессия перечитала 3 844 карточки Тендер.Про полным
текстом (прежде комментарий обрезался на 1 500 знаках, и половина людей до
разбора не доходила) и выложила `VAZHNOE-3s-TENDERPRO-lica.csv`: 2 387 человек,
534 в технических ролях, 2 142 с телефоном. Это ровно то, что у меня стояло
задачей «перечитать карточки Тендер.Про» — работа уже сделана соседкой.

ПОЧЕМУ ФАЙЛ НЕЛЬЗЯ ПРОСТО ВЛИТЬ. Колонка `inn` в нём ПУСТА во всех 2 387
строках — замерено, а не предположено. Без ИНН строка не привязывается ни к
предприятию панели, ни к чему-либо ещё; файл выглядит богатым и не даёт нуля.

ДВА МОСТА, И ВЫБРАН ВТОРОЙ:
  * через `tender_id` и наши собственные ссылки на тендеры в enrich.db —
    проверено, у нас известны ИНН только 35 тендеров, пересечение с их набором
    НУЛЕВОЕ. Мост не работает;
  * через ИМЯ КОМПАНИИ. Разных компаний в файле всего 114, и 1 097 строк
    совпадают с названием предприятия панели ТОЧНО после нормализации (снятие
    кавычек и организационно-правовой формы). Берём только ОДНОЗНАЧНЫЕ
    совпадения: если нормализованное имя ведёт на два ИНН, строка пропускается
    и считается. Похожесть не используем вовсе — «Химпром» и «Химпром
    (Новочебоксарск)» это разные юрлица, и ошибка здесь означает чужой телефон
    в карточке предприятия.

Роль берём НЕ из их колонки `rol` (там три значения: снабжение, техническая,
неясно), а из должности нашим каноном — тем же, что размечает всю базу.

По умолчанию СУХОЙ ПРОГОН. Запуск: python dolivka_tenderpro_3s.py [--apply]
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
ФАЙЛ = 'VAZHNOE-3s-TENDERPRO-lica.csv'
ПРИМЕНИТЬ = '--apply' in sys.argv
_ДОБ = re.compile(r'\s*(?:доб|вн|внутр|ext)\.?\s*[:№]?\s*[\d\-]+\s*$', re.I)
_ОПФ = re.compile(
    r'\b(ооо|оао|зао|ао|пао|мУп|муп|гуп|фгуп|нао|ано|фгбу|фку|гк)\b|'
    r'общество\s+с\s+ограниченной\s+ответственностью|'
    r'акционерное\s+общество|публичное|непубличное', re.I)
_ЯРЛЫК_В_ФИО = re.compile(
    r'^\s*(?:телефон|тел|факс|почта|e-?mail|контакт\w*|приёмн\w*|приемн\w*|'
    r'начальник\w*|директор\w*|руководител\w*|менеджер\w*|специалист\w*|'
    r'инженер\w*|отдел\w*|бухгалтер\w*|секретар\w*|диспетчер\w*|мастер|'
    r'зам|заместител\w*|ответственн\w*|исполнител\w*|куратор\w*)\b', re.I)


def норм(т):
    т = re.sub(r'["«»\']', '', str(т or '').lower())
    т = _ОПФ.sub(' ', т)
    return re.sub(r'\s+', ' ', т).strip()


def клч(т):
    return re.sub(r'\s+', ' ', str(т or '').strip().lower()).replace('ё', 'е')


def д10(т):
    ц = re.sub(r'\D', '', _ДОБ.sub('', str(т or '')))
    return ц[-10:] if len(ц) >= 10 else ''


def вид_номера(ц):
    return 'нет номера' if not ц else ('мобильный' if ц.startswith('9')
                                       else 'городской')


def человек_ли(т):
    т = (т or '').strip()
    if len(т) < 4 or re.fullmatch(r'[\d\s()+\-]{4,}', т):
        return False
    if re.search(r'\b(ООО|ОАО|ЗАО|АО|ПАО|МУП|ГУП|ФГУП|УК)\b|общество|'
                 r'предприяти|учреждени|компани|организаци|акционерн|унитарн',
                 т, re.I):
        return False
    return not _ЯРЛЫК_В_ФИО.match(т)


def номер_живой(ц):
    return bool(ц) and len(set(ц)) > 2


def main():
    csv.field_size_limit(10 ** 7)
    путь = os.path.join(ДРОП, ФАЙЛ)
    if not os.path.exists(путь):
        raise SystemExit(f'нет {ФАЙЛ} на дропе сервера')
    db = EDB.EnrichDB()
    тех = set(EDB.EnrichDB.TECH_ROLES) | {'техконтакт'}

    цб = sqlite3.connect(f'file:{БАЗА}?mode=ro', uri=True, timeout=20)
    по_имени = {}
    for и, н in цб.execute('SELECT inn, predpriyatie FROM company'):
        к = норм(н)
        if к and len(к) >= 5:
            по_имени.setdefault(к, set()).add(re.sub(r'\D', '', и)[:12])
    есть_люди = {(re.sub(r'\D', '', и)[:12], клч(п)) for и, п in
                 цб.execute('SELECT inn, person FROM person') if п}
    есть_тел = set()
    for и, з in цб.execute("SELECT inn, value FROM contact WHERE kind='phone'"):
        ц = д10(з)
        if ц:
            есть_тел.add((re.sub(r'\D', '', и)[:12], ц))
    было_людей, было_тел = len(есть_люди), len(есть_тел)
    цб.close()
    print(f'в панели: разных людей {было_людей}, разных номеров {было_тел}')

    нов_люди, нов_тел = [], []
    отсев = Counter()
    роли_новых = Counter()
    предпр = set()
    прочитано = 0
    with open(путь, encoding='utf-8-sig', errors='replace', newline='') as ф:
        for r in csv.DictReader(ф, delimiter=';'):
            прочитано += 1
            цели = по_имени.get(норм(r.get('company')), set())
            if not цели:
                отсев['компании нет в панели'] += 1
                continue
            if len(цели) > 1:
                # одно имя на два юрлица: привязать наугад значит подложить
                # продавцу чужой контакт
                отсев['имя ведёт на несколько ИНН'] += 1
                continue
            и = next(iter(цели))
            имя = (r.get('imya') or '').strip()
            если = (r.get('dolzhnost') or '').strip()
            тел = (r.get('telefon') or '').strip()
            поч = (r.get('pochta') or '').strip()
            осн = (r.get('osnovanie') or '').strip()
            тид = (r.get('tender_id') or '').strip()
            ссылка = f'https://www.tender.pro/tender/{тид}' if тид else ''
            if имя and not человек_ли(имя):
                отсев['в поле человека ярлык или организация'] += 1
                continue
            if not (тел or поч):
                отсев['ни телефона, ни почты'] += 1
                continue
            ц = д10(тел)
            if ц and not номер_живой(ц):
                отсев['номер-заглушка'] += 1
                ц = ''
            # РОЛЬ ПО ДОЛЖНОСТИ НАШИМ КАНОНОМ, а не по их трём значениям
            роль = ''
            try:
                роль = EDB.EnrichDB._canon_role(если or (r.get('rol') or ''))
            except Exception:  # noqa: BLE001
                роль = ''
            техн = 1 if роль in тех else 0

            if имя:
                к = (и, клч(имя))
                if к not in есть_люди:
                    есть_люди.add(к)
                    предпр.add(и)
                    роли_новых[роль or 'роль не установлена'] += 1
                    нов_люди.append((
                        и, имя, (если or осн)[:120],
                        роль or 'роль не установлена', тел or None,
                        вид_номера(ц), поч or None, ссылка or None,
                        'Тендер.Про, полная карточка (сбор 3-й сессии)', техн))
            if ц and (и, ц) not in есть_тел:
                есть_тел.add((и, ц))
                предпр.add(и)
                нов_тел.append((
                    и, тел[:60], 'phone', имя or None, роль or None,
                    (если or осн)[:120] or None, вид_номера(ц),
                    'Тендер.Про, полная карточка (сбор 3-й сессии)',
                    ссылка or None, 1 if роль == 'снабжение/закупки' else 0,
                    техн, 1 if (имя or роль) else 0, 0 if имя else 1))

    print(json.dumps({
        'строк_прочитано': прочитано,
        'НОВЫХ_людей': len(нов_люди),
        'из_них_ТЕХНИЧЕСКИХ': sum(1 for с in нов_люди if с[9]),
        'НОВЫХ_номеров': len(нов_тел),
        'из_них_мобильных': sum(1 for с in нов_тел if с[6] == 'мобильный'),
        'предприятий_затронуто': len(предпр),
        'роли_новых_людей': роли_новых.most_common(10),
        'отсеяно': отсев.most_common(8),
        'режим': 'ПРИМЕНЕНИЕ' if ПРИМЕНИТЬ else 'сухой (--apply)',
    }, ensure_ascii=False, indent=1))
    for с in нов_люди[:10]:
        if с[9]:
            print(f'  техЛПР {с[0]}  {с[1][:26]:<26} {с[3][:18]:<18} '
                  f'{с[2][:40]}  {с[4] or с[6] or ""}')

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
                   "VALUES ('dolito_tenderpro_3s', ?)",
                   (time.strftime('%Y-%m-%dT%H:%M:%S'),))
        cx.commit()
    finally:
        cx.close()

    цб = sqlite3.connect(f'file:{БАЗА}?mode=ro', uri=True, timeout=20)
    пары_л = len({(re.sub(r'\D', '', и)[:12], клч(п)) for и, п in
                  цб.execute('SELECT inn, person FROM person') if п})
    пары_т = len({(re.sub(r'\D', '', и)[:12], д10(з)) for и, з in
                  цб.execute("SELECT inn, value FROM contact WHERE kind='phone'")
                  if д10(з)})
    цб.close()
    # ДВА РАЗНЫХ КЛЮЧА, А НЕ ОДИН. В первой версии и люди, и номера писались
    # ключом «стало», второй затирал первый, и в отчёте о доливке людей
    # красовалось число телефонов. Отчёт, который врёт про собственный
    # результат, хуже отсутствующего.
    print(json.dumps({'разных_людей_было': было_людей,
                      'разных_людей_стало': пары_л,
                      'разных_номеров_было': было_тел,
                      'разных_номеров_стало': пары_т}, ensure_ascii=False))

    имя_ф = 'DOLIVKA-tenderpro-3s-ot-1-sessii.csv'
    п = os.path.join(r'C:\sender\server', имя_ф)
    with open(п, 'w', encoding='utf-8-sig', newline='') as ф:
        в = csv.writer(ф, delimiter=';')
        в.writerow(['inn', 'fio', 'dolzhnost', 'rol', 'telefon', 'vid',
                    'pochta', 'ssylka', 'istochnik', 'tehLPR'])
        for с in нов_люди:
            в.writerow(с)
    try:
        урл = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop')
        urllib.request.urlopen(urllib.request.Request(
            урл.rstrip('/') + '/' + имя_ф, data=open(п, 'rb').read(),
            method='PUT',
            headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}),
            timeout=300).read()
        print(f'для сборщика: {имя_ф} на дропе')
    except Exception as e:  # noqa: BLE001
        print(f'файл не ушёл на дроп: {e}')


if __name__ == '__main__':
    main()
