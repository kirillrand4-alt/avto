# -*- coding: utf-8 -*-
"""Завести телефоны и почты чеко НАСТОЯЩИМИ контактами, а не текстом в карточке.

ЗАЧЕМ. Сбор с чеко дал 7 007 пар «предприятие + номер» и 1 356 наборов почт, но
легли они в колонки карточки `telefony_checko` / `pochty_checko`. Для продавца
это почти бесполезно: такой номер не виден фильтру «есть телефон», у него нет
владельца и роли, он не попадает в очередь обзвона. Замер: из 7 007 пар в
таблице `contact` уже есть 1 337, а 5 670 не заведены вовсе.

ЧТО ДЕЛАЕМ. Каждый номер и почту заводим строкой в `contact` с источником
«чеко» и ссылкой на карточку компании. Владельца НЕ выдумываем: чеко даёт
контакты предприятия, а не человека, поэтому `person` пустой, `role` пустая,
`is_unknown_owner=1`. Это честное состояние «номер есть, чей — не установлено»,
и оно лучше и пустого поля, и выдуманной роли.

ОБЩИЕ НОМЕРА. Прогоняем через то же правило, что и панель: номер, стоящий у
2+ предприятий с РАЗНЫМИ фамилиями, роли не получает никогда. Здесь роли и так
нет, но помечаем такие номера явно, чтобы продавец видел «линия площадки».

ПОЧЕМУ ПРЯМО В centrifugal.db. Таблица `contact` пересобирается билдом, но
источник пересборки — enrich.db, поэтому пишем в ОБА: в enrich.db (переживёт
пересборку) и в снимок панели (видно сразу, до следующей пересборки).

По умолчанию СУХОЙ ПРОГОН. Запуск: python zalit_kontakty_checko.py [--apply]
"""
import json
import os
import re
import shutil
import sqlite3
import sys
import time
from collections import Counter

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

ЦБ = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
ПРИМЕНИТЬ = '--apply' in sys.argv
ИСТОЧНИК = 'чеко: контакты компании'


def цифры10(з):
    d = re.sub(r'\D', '', str(з or ''))
    return d[-10:] if len(d) >= 10 else ''


def годный_номер(ц10):
    """Тот же фильтр, что при сборе: код региона из 3/4/8/9."""
    return len(ц10) == 10 and ц10[0] in '3489'


def main():
    db = EDB.EnrichDB()
    цб_ro = sqlite3.connect(f'file:{ЦБ}?mode=ro', uri=True, timeout=20)
    наши = {str(r[0]) for r in цб_ro.execute('SELECT inn FROM company')}
    было_тел = set()
    было_поч = set()
    for инн, вид, зн in цб_ro.execute(
            "SELECT inn, COALESCE(kind,''), COALESCE(value,'') FROM contact"):
        if вид == 'phone':
            было_тел.add((str(инн), цифры10(зн)))
        elif вид == 'email':
            было_поч.add((str(инн), str(зн).strip().lower()))
    цб_ro.close()

    # карта общих номеров: 2+ предприятий => линия площадки
    сколько_инн = Counter()
    строки = list(db.cx.execute(
        "SELECT inn, COALESCE(phones_checko,''), COALESCE(emails_checko,''), "
        "COALESCE(site_checko,'') FROM requisites"))
    for инн, тел, _п, _с in строки:
        for t in str(тел).split('|'):
            ц = цифры10(t)
            if годный_номер(ц):
                сколько_инн[ц] += 1

    новые_тел, новые_поч = [], []
    стат = Counter()
    for инн, тел, поч, сайт in строки:
        инн = str(инн)
        if инн not in наши:
            стат['предприятия нет в панели'] += 1
            continue
        урл = f'https://checko.ru/company/inn/{инн}'
        for t in str(тел).split('|'):
            ц = цифры10(t)
            if not годный_номер(ц):
                continue
            if (инн, ц) in было_тел:
                стат['телефон уже был'] += 1
                continue
            общий = сколько_инн[ц] > 1
            новые_тел.append((инн, '+7' + ц, 'phone',
                              ИСТОЧНИК + ('; общий номер: несколько предприятий'
                                          if общий else ''), урл, 1))
            было_тел.add((инн, ц))
            стат['ОБЩИХ среди новых' if общий else 'телефонов к заливке'] += 1
        for e in str(поч).split('|'):
            а = e.strip().lower()
            if not а or '@' not in а:
                continue
            if (инн, а) in было_поч:
                стат['почта уже была'] += 1
                continue
            новые_поч.append((инн, а, 'email', ИСТОЧНИК, урл, 1))
            было_поч.add((инн, а))
            стат['почт к заливке'] += 1

    print(json.dumps({'предприятий в requisites': len(строки),
                      'ТЕЛЕФОНОВ К ЗАЛИВКЕ': len(новые_тел),
                      'ПОЧТ К ЗАЛИВКЕ': len(новые_поч),
                      'разбивка': стат.most_common(),
                      'режим': 'ПРИМЕНЕНИЕ' if ПРИМЕНИТЬ else 'сухой (--apply)'},
                     ensure_ascii=False, indent=1))
    for р in новые_тел[:5]:
        print(f'  + {р[0]} {р[1]} [{р[3][:52]}]')
    if not ПРИМЕНИТЬ or not (новые_тел or новые_поч):
        if not ПРИМЕНИТЬ:
            print('\nсухой прогон. Повторить с --apply')
        return

    коп = ЦБ + '.bak-' + str(int(time.time()))
    shutil.copy2(ЦБ, коп)
    print(f'бэкап: {os.path.basename(коп)}')
    cx = sqlite3.connect(ЦБ, timeout=120)
    cx.execute('PRAGMA busy_timeout=120000')
    кол = {c[1] for c in cx.execute('PRAGMA table_info(contact)')}
    поля = ['inn', 'value', 'kind', 'source', 'source_url']
    ряды = [(и, з, в, ис, у) for и, з, в, ис, у, _н in новые_тел + новые_поч]
    if 'is_unknown_owner' in кол:
        поля.append('is_unknown_owner')
        ряды = [р + (1,) for р in ряды]
    было_всего = cx.execute('SELECT COUNT(*) FROM contact').fetchone()[0]
    cx.executemany(
        f'INSERT INTO contact ({",".join(поля)}) '
        f'VALUES ({",".join("?" * len(поля))})', ряды)
    cx.commit()
    стало = cx.execute('SELECT COUNT(*) FROM contact').fetchone()[0]
    тел_всего = cx.execute(
        "SELECT COUNT(*) FROM contact WHERE kind='phone'").fetchone()[0]
    предпр_с_тел = cx.execute(
        "SELECT COUNT(DISTINCT inn) FROM contact WHERE kind='phone'").fetchone()[0]
    cx.close()
    print(json.dumps({'контактов было': было_всего, 'стало': стало,
                      'добавлено': стало - было_всего,
                      'телефонов в базе': тел_всего,
                      'ПРЕДПРИЯТИЙ С ТЕЛЕФОНОМ': предпр_с_тел},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
