# -*- coding: utf-8 -*-
"""Снять с общих номеров ярлык личного технического контакта.

ЗАЧЕМ. Аудит нашёл в панели 293 записи, где один номер стоит у РАЗНЫХ
предприятий, и 205, где он стоит у разных людей одного предприятия. Из них 39
помечены как ЛИЧНЫЙ ТЕХНИЧЕСКИЙ. Для продавца это худший вид ошибки: он видит
«главный инженер, прямой номер», звонит и попадает на коммутатор, который мы
уже отдали трём другим заводам. Номер `4957775500` стоит сразу у четырёх ИНН.

ЧТО ДЕЛАЕМ И ЧЕГО НЕ ДЕЛАЕМ. Не удаляем ничего: ни номер, ни фамилию. Номер
предприятия — ценность, через него дозваниваются, а фамилия нужна, чтобы
попросить конкретного человека у секретаря. Снимаем ровно ложное утверждение:
пометку «личный технический» и роль, по которой считается фильтр «телефон с
ролью» — иначе коммутатор всплывает наверх списка как прямой номер технаря.
Номер остаётся видимым, с честной подписью, сколько людей или предприятий его
делят.

ПОЧЕМУ НЕ ВСЕХ ПОДРЯД. Один номер на несколько людей ОДНОГО предприятия — это
нормальный коммутатор, и таких 205. Ложь здесь только в привязке к конкретному
человеку, сам номер верен. А номер на РАЗНЫХ предприятиях — уже подозрителен
сам по себе: либо это федеральный колл-центр, либо мы его кому-то приписали
зря. Такие помечаем отдельно и жёстче.

Исключение, которое нельзя стричь: холдинг. У «Газпром нефтехим Салават» и его
дочернего ООО один московский номер законно. Поэтому мы номер НЕ удаляем ни в
одном случае — только снимаем личную привязку.

База панели read-only пересобирается офлайн, поэтому правка идёт с копией и
дублируется файлом для сборщика.

По умолчанию СУХОЙ ПРОГОН. Запуск: python chistka_obshchih_v_paneli.py [--apply]
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
from collections import defaultdict

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

БАЗА = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
ПРИМЕНИТЬ = '--apply' in sys.argv
ИМЯ = 'CHISTKA-obshchie-nomera-v-paneli.csv'
ТЕХ = set(EDB.EnrichDB.TECH_ROLES) | {'техконтакт'}
_ДОБ = re.compile(r'\s*(?:доб|вн|внутр|ext)\.?\s*[:№]?\s*[\d\-]+\s*$', re.I)


def д10(т):
    ц = re.sub(r'\D', '', _ДОБ.sub('', str(т or '')))
    return ц[-10:] if len(ц) >= 10 else ''


def клч(т):
    return re.sub(r'\s+', ' ', str(т or '').strip().lower()).replace('ё', 'е')


def main():
    цб = sqlite3.connect(f'file:{БАЗА}?mode=ro', uri=True, timeout=20)
    строки = list(цб.execute(
        "SELECT rowid, inn, value, COALESCE(person,''), COALESCE(role,''), "
        "COALESCE(is_tech,0), COALESCE(source,'') FROM contact "
        "WHERE kind='phone'"))
    цб.close()

    по_номеру = defaultdict(lambda: {'инн': set(), 'люди': set(), 'ряды': []})
    for rid, инн, зн, чел, роль, тех, ист in строки:
        ц = д10(зн)
        if not ц:
            continue
        з = по_номеру[ц]
        з['инн'].add(str(инн))
        if клч(чел):
            з['люди'].add(клч(чел))
        з['ряды'].append((rid, str(инн), зн, чел, роль, тех, ист))

    правки, примеры = [], []
    счёт = {'номер у разных предприятий': 0,
            'номер у разных людей одного предприятия': 0,
            'снимаем пометку ТЕХНИЧЕСКИЙ': 0,
            'снимаем роль у номера': 0}
    for ц, з in по_номеру.items():
        много_инн = len(з['инн']) > 1
        много_людей = len(з['люди']) > 1
        if not (много_инн or много_людей):
            continue
        подпись = (f'общий номер: встречается у {len(з["инн"])} предприятий'
                   if много_инн
                   else f'общий номер предприятия: {len(з["люди"])} человек')
        for rid, инн, зн, чел, роль, тех, ист in з['ряды']:
            if not (чел or тех):
                continue          # уже без владельца — трогать нечего
            счёт['номер у разных предприятий' if много_инн
                 else 'номер у разных людей одного предприятия'] += 1
            if тех:
                счёт['снимаем пометку ТЕХНИЧЕСКИЙ'] += 1
            if роль:
                счёт['снимаем роль у номера'] += 1
            новый_ист = (ист + ('; ' if ист else '') + подпись)[:200]
            правки.append((новый_ист, rid))
            if len(примеры) < 15:
                примеры.append(
                    f'  {инн} {зн[:20]:<20} {(чел or "без владельца")[:26]:<26} '
                    f'{роль[:16]:<16} {"ТЕХ" if тех else "   "}  {подпись}')

    print(json.dumps({
        'записей_телефонов_в_панели': len(строки),
        'ПРАВОК': len(правки),
        **счёт,
        'режим': 'ПРИМЕНЕНИЕ' if ПРИМЕНИТЬ else 'сухой (--apply)',
    }, ensure_ascii=False, indent=1))
    for п in примеры:
        print(п)

    if not ПРИМЕНИТЬ or not правки:
        if not ПРИМЕНИТЬ:
            print('\nсухой прогон. Повторить с --apply')
        return

    коп = БАЗА + '.bak-' + str(int(time.time()))
    shutil.copy2(БАЗА, коп)
    print(f'копия базы: {os.path.basename(коп)}')
    cx = sqlite3.connect(БАЗА, timeout=60)
    try:
        # ИМЯ ЧЕЛОВЕКА ОСТАЁТСЯ, снимается только ложное утверждение. Первая
        # версия стирала и человека — это потеря: через коммутатор продавец
        # спрашивает «позовите Никифорова», и знать фамилию ему нужно. Ложь
        # здесь не в том, что человек есть, а в том, что номер ЕГО ЛИЧНЫЙ и
        # технический. Роль снимаем, потому что по ней считается фильтр
        # «телефон с ролью» — иначе коммутатор снова всплывёт наверх списка.
        cx.executemany(
            "UPDATE contact SET role=NULL, is_tech=0, has_role=0, source=? "
            "WHERE rowid=?", правки)
        cx.execute("INSERT OR REPLACE INTO import_info (key, value) "
                   "VALUES ('chistka_obshchih_nomerov', ?)",
                   (time.strftime('%Y-%m-%dT%H:%M:%S'),))
        cx.commit()
    finally:
        cx.close()

    цб = sqlite3.connect(f'file:{БАЗА}?mode=ro', uri=True, timeout=20)
    осталось = цб.execute(
        "SELECT COUNT(*) FROM contact WHERE kind='phone' "
        "AND COALESCE(is_tech,0)=1 AND COALESCE(person,'')<>''").fetchone()[0]
    предпр = цб.execute(
        "SELECT COUNT(DISTINCT inn) FROM contact WHERE kind='phone' "
        "AND COALESCE(is_tech,0)=1 AND COALESCE(person,'')<>''").fetchone()[0]
    цб.close()
    print(json.dumps({
        'правок_применено': len(правки),
        'осталось_личных_технических_номеров': осталось,
        'на_предприятиях': предпр}, ensure_ascii=False))

    п = os.path.join(r'C:\sender\server', ИМЯ)
    with open(п, 'w', encoding='utf-8-sig', newline='') as ф:
        в = csv.writer(ф, delimiter=';')
        в.writerow(['rowid', 'novyy_istochnik'])
        в.writerows([(r[1], r[0]) for r in правки])
    try:
        урл = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop')
        urllib.request.urlopen(urllib.request.Request(
            урл.rstrip('/') + '/' + ИМЯ, data=open(п, 'rb').read(),
            method='PUT',
            headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}),
            timeout=300).read()
        print(f'для сборщика: {ИМЯ} на дропе')
    except Exception as e:  # noqa: BLE001
        print(f'файл не ушёл на дроп: {e}')


if __name__ == '__main__':
    main()
