# -*- coding: utf-8 -*-
"""Влить людей 2-й сессии из DLYA-1-SESSII-lyudi-2s.csv — только НОВОЕ.

ЧЕСТНЫЙ РАЗМЕР ПРИРОСТА. В файле 1 858 строк, и легко принять это число за
находку — я сам так и доложил владельцу, пока не сверил. Сверка: наших ИНН
1 788, с личным номером 248, но 225 из них УЖЕ в базе (мы с соседкой черпаем из
общих источников — Тендер.Про, сайты). Настоящий прирост: 23 номера, 21 человек,
из них технических 7, на 8 предприятиях.

ПОЧЕМУ ВСЁ РАВНО ЛЬЁМ. Это ЛИЧНЫЕ мобильные с именем и ролью, а у нас телефон
И роль есть всего у 37 компаний из 1 573. Двадцать три личных номера на этом
фоне — не мелочь, а +8 предприятий, куда продавец сможет позвонить человеку,
а не на завод.

ЧТО ПРОВЕРЕНО ПЕРЕД ЗАЛИВКОЙ: ни один из 23 номеров не встречается в файле
дважды (то есть это не одна линия, размазанная по людям); источники —
официальные страницы контактов (nnk.ru/contacts/contact-suppliers) и карточки
закупок. Дополнительно прогоняем через общее правило: номер, стоящий у 2+
РАЗНЫХ предприятий, роли не получает.

Пишем в contact (номер) и person (человек с ролью), источник — с пометкой, что
данные от 2-й сессии, со ссылкой из файла. По умолчанию СУХОЙ ПРОГОН.
Запуск: python zalit_lyudey_2s.py [--apply]
"""
import csv
import json
import os
import re
import shutil
import sqlite3
import sys
import time
from collections import Counter

ЦБ = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
ФАЙЛ = os.path.join(r'C:\seostat\drop\drop-storage', 'DLYA-1-SESSII-lyudi-2s.csv')
ПРИМЕНИТЬ = '--apply' in sys.argv
ИСТОЧНИК = 'свод 2-й сессии (личные номера)'


def ц10(з):
    d = re.sub(r'\D', '', str(з or ''))
    return d[-10:] if len(d) >= 10 else ''


def фамилия(ч):
    ч = re.sub(r'[^А-Яа-яЁёA-Za-z\s.-]', ' ', str(ч or '')).strip()
    return ч.split()[0].lower() if ч.split() else ''


def main():
    csv.field_size_limit(10 ** 7)
    if not os.path.exists(ФАЙЛ):
        raise SystemExit(f'нет {os.path.basename(ФАЙЛ)} на дропе')
    цб = sqlite3.connect(f'file:{ЦБ}?mode=ro', uri=True, timeout=20)
    наши = {str(r[0]) for r in цб.execute('SELECT inn FROM company')}
    есть_ном = set()
    инн_по_номеру = {}
    for и, v in цб.execute("SELECT inn, value FROM contact WHERE kind='phone'"):
        к = ц10(v)
        if к:
            есть_ном.add((str(и), к))
            инн_по_номеру.setdefault(к, set()).add(str(и))
    есть_чел = {(str(и), фамилия(ч)) for и, ч in цб.execute(
        "SELECT inn, COALESCE(person,'') FROM person WHERE COALESCE(person,'')<>''")}
    цб.close()

    нов_ном, нов_чел = [], []
    стат = Counter()
    with open(ФАЙЛ, encoding='utf-8-sig', errors='replace', newline='') as ф:
        for r in csv.DictReader(ф, delimiter=';'):
            и = re.sub(r'\D', '', str(r.get('inn') or ''))
            ном = ц10(r.get('lichnyy_nomer')) or ц10(r.get('mobilnyy'))
            чел = str(r.get('chelovek') or '').strip()
            роль = str(r.get('rol') or '').strip()
            долж = str(r.get('dolzhnost') or '').strip()
            тех = str(r.get('tehnicheskiy', '')).strip().lower() in (
                'да', '1', 'true', 'yes')
            ссыл = str(r.get('ssylki') or '').split(';')[0].strip()
            if not и or и not in наши or not ном:
                стат['мимо (нет ИНН/номера/не наш)'] += 1
                continue
            if (и, ном) in есть_ном:
                стат['номер уже был'] += 1
                continue
            # общий номер: стоит у другого предприятия — роль не даём
            общий = len(инн_по_номеру.get(ном, set()) - {и}) > 0
            если_роль = '' if общий else роль
            нов_ном.append((и, '+7' + ном, 'phone',
                            ИСТОЧНИК + ('; общий номер' if общий else ''),
                            ссыл, 1 if тех and not общий else 0,
                            1 if общий else 0))
            есть_ном.add((и, ном))
            стат['ОБЩИХ среди новых' if общий else 'номеров к заливке'] += 1
            if чел and (и, фамилия(чел)) not in есть_чел:
                нов_чел.append((и, чел, долж or роль, если_роль, '+7' + ном,
                                ИСТОЧНИК, ссыл, 1 if тех else 0))
                есть_чел.add((и, фамилия(чел)))
                стат['людей к заливке'] += 1
                if тех:
                    стат['  из них технических'] += 1

    print(json.dumps({'номеров': len(нов_ном), 'людей': len(нов_чел),
                      'разбивка': стат.most_common(),
                      'режим': 'ПРИМЕНЕНИЕ' if ПРИМЕНИТЬ else 'сухой (--apply)'},
                     ensure_ascii=False, indent=1))
    for р in нов_чел[:6]:
        print(f'  + {р[0]} {р[1][:28]:28} {р[3][:14]:14} {р[4]}')
    if not ПРИМЕНИТЬ or not нов_ном:
        if not ПРИМЕНИТЬ:
            print('\nсухой прогон. Повторить с --apply')
        return

    коп = ЦБ + '.bak-' + str(int(time.time()))
    shutil.copy2(ЦБ, коп)
    print(f'бэкап: {os.path.basename(коп)}')
    cx = sqlite3.connect(ЦБ, timeout=120)
    cx.execute('PRAGMA busy_timeout=120000')
    кк = {c[1] for c in cx.execute('PRAGMA table_info(contact)')}
    пк = {c[1] for c in cx.execute('PRAGMA table_info(person)')}
    было_к = cx.execute('SELECT COUNT(*) FROM contact').fetchone()[0]
    было_п = cx.execute('SELECT COUNT(*) FROM person').fetchone()[0]
    поля_к = ['inn', 'value', 'kind', 'source', 'source_url']
    ряды_к = [(и, з, в, ист, у) for и, з, в, ист, у, _т, _о in нов_ном]
    if 'is_tech' in кк:
        поля_к.append('is_tech')
        ряды_к = [р + (нов_ном[i][5],) for i, р in enumerate(ряды_к)]
    if 'is_unknown_owner' in кк:
        поля_к.append('is_unknown_owner')
        ряды_к = [р + (нов_ном[i][6],) for i, р in enumerate(ряды_к)]
    cx.executemany(f'INSERT INTO contact ({",".join(поля_к)}) '
                   f'VALUES ({",".join("?" * len(поля_к))})', ряды_к)
    поля_п = [к for к in ('inn', 'person', 'position', 'role', 'phone',
                          'source', 'source_url', 'is_tech') if к in пк]
    сопост = {'inn': 0, 'person': 1, 'position': 2, 'role': 3, 'phone': 4,
              'source': 5, 'source_url': 6, 'is_tech': 7}
    cx.executemany(f'INSERT INTO person ({",".join(поля_п)}) '
                   f'VALUES ({",".join("?" * len(поля_п))})',
                   [tuple(р[сопост[к]] for к in поля_п) for р in нов_чел])
    cx.commit()
    стало_к = cx.execute('SELECT COUNT(*) FROM contact').fetchone()[0]
    стало_п = cx.execute('SELECT COUNT(*) FROM person').fetchone()[0]
    с_тел_ролью = cx.execute(
        "SELECT COUNT(DISTINCT inn) FROM contact WHERE kind='phone' "
        "AND COALESCE(is_tech,0)=1").fetchone()[0]
    cx.close()
    print(json.dumps({'контактов': f'{было_к} -> {стало_к}',
                      'людей': f'{было_п} -> {стало_п}',
                      'предприятий с техтелефоном': с_тел_ролью},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
