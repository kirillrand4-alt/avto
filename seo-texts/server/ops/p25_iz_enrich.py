# -*- coding: utf-8 -*-
"""P25: перелить улов чеко из enrich.db в p25.db с наблюдениями.

ОТКУДА. Штатный `checko_contacts.py` прошёл по 491 ИНН P25 и записал в
enrich.db: 1 040 телефонов, 908 почт, 115 руководителей — каждый со ссылкой на
ту страницу чеко, с которой снят. Второй обходчик я не писал: чужой обкатан,
резюмируем и уже пишет провенанс.

ЧЕЙ ЭТО НОМЕР. Чеко подписи «директор / бухгалтерия» рядом с номером НЕ даёт —
владелец подтвердил прямо. Значит это номера ПРЕДПРИЯТИЯ, и заводить под них
человека нельзя. Пишу их как есть: `person` пустой, `is_unknown_owner=1`,
`phone_type='общий'`. Честное «номер есть, чей — не установлено» лучше и пустого
поля, и выдуманной роли.

РУКОВОДИТЕЛЬ — ДРУГОЕ ДЕЛО. У него на карточке есть ФИО и должность, он идёт в
`person` с ролью «4 круг» (руководство): по ТЗ его берут, только если выше
никого не нашли, и в главную меру он не идёт.

ДАТА НАБЛЮДЕНИЯ — дата опроса чеко. Это честно: «на эту дату номер стоял на
карточке». Не дата регистрации юрлица и не дата файла.

Запуск: python p25_iz_enrich.py [--apply]
"""
import io
import json
import os
import re
import sqlite3
import sys
import time
from collections import Counter

P25 = r'C:\seostat\data\p25.db'
ПОТОК = r'C:\seostat\drop\p25_iz_enrich.jsonl'
ПРИМЕНИТЬ = '--apply' in sys.argv
sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402


def номер(з):
    ц = re.sub(r'\D', '', str(з or ''))
    if len(ц) == 10:
        ц = '7' + ц
    if len(ц) == 11 and ц[0] == '8':
        ц = '7' + ц[1:]
    return '+' + ц if len(ц) == 11 and ц[0] == '7' else ''


def main():
    db = EDB.EnrichDB()
    цб = sqlite3.connect(P25, timeout=30)
    наши = {str(r[0]) for r in цб.execute('SELECT inn FROM company')}
    поля_c = [r[1] for r in цб.execute('PRAGMA table_info(contact)')]
    поля_p = [r[1] for r in цб.execute('PRAGMA table_info(person)')]
    было_c = цб.execute('SELECT COUNT(*) FROM contact').fetchone()[0]
    было_p = цб.execute('SELECT COUNT(*) FROM person').fetchone()[0]
    было_s = цб.execute('SELECT COUNT(*) FROM contact_source').fetchone()[0]

    стат = Counter()
    записи = []

    # ТЕЛЕФОНЫ И ПОЧТЫ ЧЕКО
    for табл, вид, поле in (('phone_contacts', 'phone', 'phone'),
                            ('emails', 'email', 'email')):
        try:
            кур = db.cx.execute(
                f"SELECT inn, {поле}, COALESCE(source,''), COALESCE(source_url,''), "
                f"COALESCE(updated_at,'') FROM {табл} "
                f"WHERE COALESCE(source,'') LIKE 'checko%'")
        except Exception as ex:  # noqa: BLE001
            print(табл, str(ex)[:90])
            continue
        for инн, зн, ист, url, когда in кур.fetchall():
            и = str(инн)
            if и not in наши:
                continue
            значение = номер(зн) if вид == 'phone' else str(зн or '').strip().lower()
            if not значение:
                стат[f'{вид}: не разобрался'] += 1
                continue
            стат[f'{вид}: к записи'] += 1
            записи.append({'inn': и, 'kind': вид, 'value': значение,
                           'url': url, 'date': (когда or '')[:10],
                           'src': 'чеко: карточка компании'})

    # РУКОВОДИТЕЛИ
    рук = []
    try:
        for инн, фио, долж in db.cx.execute(
                "SELECT inn, COALESCE(director,''), COALESCE(director_post,'') "
                "FROM companies WHERE COALESCE(director,'')<>''"):
            и = str(инн)
            if и in наши and len(str(фио).split()) >= 2:
                рук.append((и, ' '.join(str(фио).split()), str(долж or 'руководитель')))
    except Exception as ex:  # noqa: BLE001
        print('companies:', str(ex)[:90])
    стат['руководителей к записи'] = len(рук)

    print(json.dumps(dict(стат.most_common()), ensure_ascii=False, indent=1))
    for з in записи[:6]:
        print(f"   {з['inn']} {з['kind']:6} {з['value'][:30]:30} {з['url'][:52]}")
    for и, ф, д in рук[:4]:
        print(f"   {и} РУК   {ф[:30]:30} {д[:40]}")

    if not ПРИМЕНИТЬ:
        print('\nСУХОЙ ПРОГОН, ничего не записано')
        цб.close()
        return

    ts = time.strftime('%Y-%m-%dT%H:%M:%S')
    сегодня = time.strftime('%Y-%m-%d')

    def вставить(табл, поля, зн):
        имена = [к for к in поля if к in зн]
        цб.execute(f"INSERT OR IGNORE INTO {табл} ({','.join(имена)}) "
                   f"VALUES ({','.join('?' * len(имена))})",
                   [зн[к] for к in имена])

    for з in записи:
        дата = з['date'] or сегодня
        вставить('contact', поля_c, {
            'inn': з['inn'], 'kind': з['kind'], 'value': з['value'],
            'person': '', 'role': '', 'phone_type': 'общий',
            'source': з['src'], 'source_url': з['url'],
            'data_podtverzhdeniya': дата,
            'chem_podtverzhdena': 'номер на карточке чеко, подписи чей — нет',
            'is_unknown_owner': 1, 'is_tech': 0})
        цб.execute(
            "INSERT OR IGNORE INTO contact_source(inn, contact_value, person, "
            "source, source_url, date_observed, quote, added_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (з['inn'], з['value'], '', з['src'], з['url'], дата,
             'снято с карточки чеко; подписи, чей номер, источник не даёт', ts))
    for и, ф, д in рук:
        вставить('person', поля_p, {
            'inn': и, 'person': ф, 'position': д, 'role': '4 круг: руководство',
            'source': 'чеко: карточка компании', 'source_url': '',
            'data_podtverzhdeniya': сегодня,
            'chem_podtverzhdena': 'руководитель на карточке чеко',
            'is_tech': 0})
    цб.commit()

    стало_c = цб.execute('SELECT COUNT(*) FROM contact').fetchone()[0]
    стало_p = цб.execute('SELECT COUNT(*) FROM person').fetchone()[0]
    стало_s = цб.execute('SELECT COUNT(*) FROM contact_source').fetchone()[0]
    с_тел = цб.execute(
        "SELECT COUNT(DISTINCT inn) FROM contact WHERE kind='phone'").fetchone()[0]
    цб.close()

    with io.open(ПОТОК, 'a', encoding='utf-8') as ф:
        for з in записи:
            ф.write(json.dumps({**з, 'ts': ts}, ensure_ascii=False) + '\n')
        ф.flush()
        os.fsync(ф.fileno())

    print(f'\ncontact: {было_c} → {стало_c}')
    print(f'person:  {было_p} → {стало_p}')
    print(f'НАБЛЮДЕНИЙ: {было_s} → {стало_s}')
    print(f'ПРЕДПРИЯТИЙ С ТЕЛЕФОНОМ: {с_тел} из 491')


if __name__ == '__main__':
    main()
