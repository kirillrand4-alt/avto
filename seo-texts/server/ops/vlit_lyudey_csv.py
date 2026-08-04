# -*- coding: utf-8 -*-
"""Влить людей с прямыми номерами из CSV соседней сессии в панель и enrich.db.

ПЕРВЫЙ СЛУЧАЙ. `DLYA-1S-KAUSTIK-strukturnye-podrazdeleniya.csv` — 14 человек
АО «Каустик» со страницы «Структурные подразделения», у ВСЕХ прямой номер.
Владелец показал эту страницу сам: «контакты с неё не сняты». Среди них Даудова,
зам. директора по закупкам по комплектации ОБОРУДОВАНИЯ — через неё и проходит
покупка компрессора.

ОП НАПИСАН ПОД ЛЮБОЙ ТАКОЙ ФАЙЛ, а не под один Каустик: колонки
`inn; chelovek; dolzhnost; podrazdelenie; telefon; pochta; rol; ssylka` —
соседки договорились отдавать людей в этом виде.

ПИШЕМ В ТРИ МЕСТА, потому что снимок панели пересобирается, а enrich.db нет:
  person + contact в centrifugal.db  — продавец видит сразу;
  people + phone_contacts в enrich.db — переживёт пересборку;
  поток .jsonl с fsync — переживёт рестарт песочницы.

ЧЕГО НЕ ДЕЛАЕМ. Не заводим человека без ФИО из двух слов и не пишем номер, если
он уже стоит у ДРУГОГО человека этого предприятия: это признак линии отдела, и
правило то же, что везде в проекте.

Запуск: python vlit_lyudey_csv.py <файл-на-дропе.csv> [--apply]
"""
import csv
import io
import json
import os
import re
import sqlite3
import sys
import time
from collections import Counter

ЦБ = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
ОБМЕН = r'C:\seostat\drop\drop-storage'
ПОТОК = r'C:\seostat\drop\vlito_lyudey_csv.jsonl'
ПРИМЕНИТЬ = '--apply' in sys.argv
ИМЯ = next((а for а in sys.argv[1:] if а.endswith('.csv')), '')


def номер(з):
    ц = re.sub(r'\D', '', str(з or ''))
    if len(ц) == 10:
        ц = '7' + ц
    if len(ц) == 11 and ц[0] == '8':
        ц = '7' + ц[1:]
    return '+' + ц if len(ц) == 11 and ц[0] == '7' else ''


def main():
    if not ИМЯ:
        print('нужно: vlit_lyudey_csv.py <файл.csv> [--apply]')
        return
    путь = os.path.join(ОБМЕН, ИМЯ)
    if not os.path.exists(путь):
        print('НЕТ ФАЙЛА:', путь)
        return

    цб = sqlite3.connect(ЦБ, timeout=30)
    поля_p = [r[1] for r in цб.execute('PRAGMA table_info(person)')]
    поля_c = [r[1] for r in цб.execute('PRAGMA table_info(contact)')]
    print('поля person:', поля_p)
    print('поля contact:', поля_c)

    есть_люди = {}
    for инн, ч in цб.execute("SELECT inn, COALESCE(person,'') FROM person"):
        есть_люди.setdefault(str(инн), set()).add(' '.join(str(ч).split()).casefold())
    номер_чей = {}
    for инн, зн, ч in цб.execute(
            "SELECT inn, COALESCE(value,''), COALESCE(person,'') FROM contact "
            "WHERE kind='phone'"):
        номер_чей.setdefault((str(инн), номер(зн)), set()).add(
            ' '.join(str(ч).split()).casefold())

    стат = Counter()
    к_записи = []
    with io.open(путь, encoding='utf-8-sig', errors='replace', newline='') as ф:
        for р in csv.DictReader(ф, delimiter=';'):
            инн = str(р.get('inn') or '').strip()
            чел = ' '.join(str(р.get('chelovek') or '').split())
            тел = номер(р.get('telefon'))
            стат['строк в файле'] += 1
            if len(чел.split()) < 2:
                стат['пропуск: не ФИО'] += 1
                continue
            if чел.casefold() in есть_люди.get(инн, set()):
                стат['человек уже на карточке'] += 1
                continue
            чужие = номер_чей.get((инн, тел), set()) - {чел.casefold()} if тел else set()
            if чужие:
                стат['номер уже у ДРУГОГО человека — беру без номера'] += 1
                тел = ''
            стат['К ЗАПИСИ'] += 1
            к_записи.append({
                'inn': инн, 'person': чел,
                'post': str(р.get('dolzhnost') or '').strip(),
                'dept': str(р.get('podrazdelenie') or '').strip(),
                'phone': тел, 'email': str(р.get('pochta') or '').strip(),
                'role': str(р.get('rol') or '').strip(),
                'url': str(р.get('ssylka') or '').strip()})

    print(json.dumps(dict(стат.most_common()), ensure_ascii=False, indent=1))
    for з in к_записи[:16]:
        print(f"  {з['inn']} {з['person'][:32]:32} | {з['role'][:18]:18} | "
              f"{з['phone']} | {з['post'][:40]}")
    if not ПРИМЕНИТЬ:
        print('\nСУХОЙ ПРОГОН, ничего не записано')
        цб.close()
        return

    ts = time.strftime('%Y-%m-%dT%H:%M:%S')
    ИСТ = 'сайт предприятия: структурные подразделения (разбор 2-й сессии)'

    def вставить(табл, поля, зн):
        имена = [к for к in поля if к in зн]
        цб.execute(
            f"INSERT OR IGNORE INTO {табл} ({','.join(имена)}) "
            f"VALUES ({','.join('?' * len(имена))})", [зн[к] for к in имена])

    до_p = цб.execute('SELECT COUNT(*) FROM person').fetchone()[0]
    до_c = цб.execute('SELECT COUNT(*) FROM contact').fetchone()[0]
    for з in к_записи:
        вставить('person', поля_p, {
            'inn': з['inn'], 'person': з['person'], 'post': з['post'],
            'dolzhnost': з['post'], 'role': з['role'], 'rol': з['role'],
            'phone': з['phone'], 'telefon': з['phone'], 'email': з['email'],
            'source': ИСТ, 'istochnik': ИСТ, 'source_url': з['url'],
            'ssylka': з['url'], 'department': з['dept'],
            'podrazdelenie': з['dept'], 'updated_at': ts})
        if з['phone']:
            вставить('contact', поля_c, {
                'inn': з['inn'], 'kind': 'phone', 'value': з['phone'],
                'person': з['person'], 'role': з['role'], 'rol': з['role'],
                'source': ИСТ, 'istochnik': ИСТ, 'source_url': з['url'],
                'ssylka': з['url'], 'updated_at': ts})
        if з['email']:
            вставить('contact', поля_c, {
                'inn': з['inn'], 'kind': 'email', 'value': з['email'],
                'person': з['person'], 'role': з['role'], 'rol': з['role'],
                'source': ИСТ, 'istochnik': ИСТ, 'source_url': з['url'],
                'ssylka': з['url'], 'updated_at': ts})
    цб.commit()
    стало_p = цб.execute('SELECT COUNT(*) FROM person').fetchone()[0]
    стало_c = цб.execute('SELECT COUNT(*) FROM contact').fetchone()[0]
    цб.close()

    # ДУБЛЬ В ДОЛГОВЕЧНОЕ: снимок пересоберут, enrich.db останется
    в_enrich = 0
    try:
        sys.path.insert(0, r'C:\sender\server')
        import enrich_db as EDB
        db = EDB.EnrichDB()
        поля_pe = [r[1] for r in db.cx.execute('PRAGMA table_info(people)')]
        for з in к_записи:
            имена = [к for к in ('inn', 'person', 'post', 'phone', 'email',
                                 'role', 'source', 'source_url', 'updated_at')
                     if к in поля_pe]
            зн = {'inn': з['inn'], 'person': з['person'], 'post': з['post'],
                  'phone': з['phone'], 'email': з['email'], 'role': з['role'],
                  'source': ИСТ, 'source_url': з['url'], 'updated_at': ts}
            db.cx.execute(
                f"INSERT OR IGNORE INTO people ({','.join(имена)}) "
                f"VALUES ({','.join('?' * len(имена))})", [зн[к] for к in имена])
            if з['phone']:
                db.cx.execute(
                    'INSERT OR IGNORE INTO phone_contacts VALUES (?,?,?,?,?,?,?)',
                    (з['inn'], з['phone'], з['person'], з['role'],
                     'сайт: структурные подразделения', з['url'], ts))
            в_enrich += 1
        db.cx.commit()
    except Exception as ex:  # noqa: BLE001
        print('enrich.db:', str(ex)[:120])

    with io.open(ПОТОК, 'a', encoding='utf-8') as ф:
        for з in к_записи:
            ф.write(json.dumps({**з, 'ts': ts, 'file': ИМЯ},
                               ensure_ascii=False) + '\n')
        ф.flush()
        os.fsync(ф.fileno())

    print(f'\nperson: было {до_p}, стало {стало_p} (+{стало_p - до_p})')
    print(f'contact: было {до_c}, стало {стало_c} (+{стало_c - до_c})')
    print(f'в enrich.db записей проведено: {в_enrich}')


if __name__ == '__main__':
    main()
