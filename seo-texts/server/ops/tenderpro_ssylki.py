# -*- coding: utf-8 -*-
"""Вернуть ссылку на карточку Тендер.Про контактам, у которых её нет.

НАШЛА 3-я СЕССИЯ: у контактов с источником «Tender.pro (очередь ЭПБ)» пусто
поле `source_url`, хотя адрес карточки существует и строится по `tender_id`.
Её слова: «сборщик не перенёс адрес карточки». Проверил — так и есть: в снимке
панели 111 контактов и 101 человек без ссылки, а в enrich.db таких НОЛЬ. Значит
писали прямо в снимок, минуя источник, и ссылку потеряли на этом пути.

ОТКУДА БЕРЁМ АДРЕС. Из её же файла `VAZHNOE-3s-TENDERPRO-lica.csv`: там есть
`tender_id` и `company_id`, а карточка открывается как
`https://www.tender.pro/api/tender/<tender_id>/view_public` — этот вид ссылки
уже встречается в наших записях, то есть проверен.

СШИВАЕМ ПО ИНН + ТЕЛЕФОНУ, а не по имени: имя пишется по-разному («Чикуров В.В.»
и «Чикуров Владимир Васильевич»), а десять цифр номера — однозначны. Где номера
нет, пробуем ИНН + фамилию.

Пишем ТОЛЬКО туда, где ссылки нет. Существующие адреса не трогаем: там может
стоять более точный.

По умолчанию СУХОЙ ПРОГОН. Запуск: python tenderpro_ssylki.py [--apply]
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
ФАЙЛ = os.path.join(r'C:\seostat\drop\drop-storage',
                    'VAZHNOE-3s-TENDERPRO-lica.csv')
ПРИМЕНИТЬ = '--apply' in sys.argv
ШАБЛОН = 'https://www.tender.pro/api/tender/{}/view_public'


def ц10(з):
    d = re.sub(r'\D', '', str(з or ''))
    return d[-10:] if len(d) >= 10 else ''


def фам(ч):
    ч = re.sub(r'[^А-Яа-яЁёA-Za-z\s.-]', ' ', str(ч or '')).strip()
    return ч.split()[0].lower() if ч.split() else ''


def main():
    csv.field_size_limit(10 ** 7)
    if not os.path.exists(ФАЙЛ):
        raise SystemExit(f'нет {os.path.basename(ФАЙЛ)} на дропе')
    по_тел, по_фам = {}, {}
    строк = 0
    with open(ФАЙЛ, encoding='utf-8-sig', errors='replace', newline='') as ф:
        for r in csv.DictReader(ф, delimiter=';'):
            строк += 1
            тид = str(r.get('tender_id') or '').strip()
            инн = re.sub(r'\D', '', str(r.get('inn') or ''))
            # ИНН в файле 3-й сессии ПУСТ ВО ВСЕХ 3 329 строках (её известная
            # дыра, задача #36). Поэтому ключом берём телефон: десять цифр
            # однозначнее ИНН и заполнены у 3 184 строк из 3 329.
            if not тид:
                continue
            урл = ШАБЛОН.format(тид)
            т = ц10(r.get('telefon'))
            if т:
                по_тел.setdefault((инн, т), урл)
                по_тел.setdefault(('', т), урл)   # ИНН в файле пуст — ключ по номеру
            ф_ = фам(r.get('imya'))
            if ф_:
                по_фам.setdefault((инн, ф_), урл)
                по_фам.setdefault(('', ф_), урл)
    print(f'в файле 3-й сессии строк {строк}; ключей по телефону {len(по_тел)}, '
          f'по фамилии {len(по_фам)}')

    цб = sqlite3.connect(f'file:{ЦБ}?mode=ro', uri=True, timeout=20)
    правки = {'contact': [], 'person': []}
    стат = Counter()
    for т, поле_зн in (('contact', 'value'), ('person', 'phone')):
        for rid, инн, зн, чел, ист, у in цб.execute(
                f"SELECT rowid, inn, COALESCE({поле_зн},''), COALESCE(person,''), "
                f"COALESCE(source,''), COALESCE(source_url,'') FROM {т}"):
            if у.strip():
                continue
            if 'tender' not in ист.lower() and 'тендер' not in ист.lower():
                continue
            стат[f'{т}: без ссылки'] += 1
            инн = str(инн)
            урл = (по_тел.get((инн, ц10(зн))) or по_тел.get(('', ц10(зн)))
                   or по_фам.get((инн, фам(чел))))
            if урл:
                правки[т].append((урл, rid))
                стат[f'{т}: АДРЕС НАЙДЕН'] += 1
            else:
                стат[f'{т}: в файле нет этой пары'] += 1
    цб.close()
    print(json.dumps({'итог': стат.most_common(),
                      'режим': 'ПРИМЕНЕНИЕ' if ПРИМЕНИТЬ else 'сухой (--apply)'},
                     ensure_ascii=False, indent=1))
    всего = sum(len(v) for v in правки.values())
    if not ПРИМЕНИТЬ or not всего:
        if not ПРИМЕНИТЬ:
            print('сухой прогон. Повторить с --apply')
        return
    коп = ЦБ + '.bak-' + str(int(time.time()))
    shutil.copy2(ЦБ, коп)
    print('бэкап:', os.path.basename(коп))
    cx = sqlite3.connect(ЦБ, timeout=120)
    cx.execute('PRAGMA busy_timeout=120000')
    for т, ряды in правки.items():
        if ряды:
            cx.executemany(f'UPDATE {т} SET source_url=? WHERE rowid=?', ряды)
    cx.commit()
    ост = {}
    for т in ('contact', 'person'):
        ост[т] = cx.execute(
            f"SELECT COUNT(*) FROM {т} WHERE COALESCE(source_url,'')='' AND "
            f"(source LIKE '%ender%' OR source LIKE '%ендер%')").fetchone()[0]
    cx.close()
    print(json.dumps({'проставлено': {т: len(р) for т, р in правки.items()},
                      'без ссылки осталось': ост}, ensure_ascii=False))


if __name__ == '__main__':
    main()
