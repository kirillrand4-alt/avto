# -*- coding: utf-8 -*-
"""Проставить настоящий источник реквизитов и телефонов: Чеко, со ссылкой.

ЗАЧЕМ. 3-я сессия нашла: у 1 359 предприятий телефоны лежат в `telefony_checko`,
а провенанс у всех один — «заливка реквизитов 1с». Это название ОПЕРАЦИИ, а не
источника: продавец жмёт «первоисточник» и не находит ничего, потому что ссылки
нет ни одной. Владелец сказал прямо: источник — Чеко, так и указать.

ПОДПИСИ РЯДОМ С НОМЕРОМ У ЧЕКО НЕТ (владелец, 04.08). Значит имя владельца
номера из этого источника не появится никогда, и степень 3-й сессии «мобильный
предприятия, чей — не записано» верна как есть. Здесь чиним только источник.

ССЫЛКА СОБИРАЕТСЯ ИЗ ОГРН: карточка контактов Чеко — `/company/<ОГРН>/contacts`,
именно эту страницу и разбирал сборщик `checko_contacts.py`. У кого ОГРН нет —
пишем источник без ссылки, честно, а не выдуманный адрес.

ОСТОРОЖНО, ЧУЖИЕ ЗАПИСИ: трогаем только те строки, где стоит ровно «заливка
реквизитов 1с» (и пустые) — если провенанс уже назван иначе, это чей-то более
точный ответ, и затирать его нельзя.

ДОЛГОВЕЧНОСТЬ: пишем в enrich.db (переживёт пересборку панели) и в снимок
`centrifugal.db` (видно продавцу сразу).

По умолчанию СУХОЙ ПРОГОН. Запуск: python checko_istochnik.py [--apply]
"""
import io
import json
import os
import re
import sqlite3
import sys
import time
from collections import Counter

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

ЦБ = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
ПОТОК = r'C:\seostat\drop\checko_istochnik.jsonl'
ПРИМЕНИТЬ = '--apply' in sys.argv
СТАРОЕ = ('заливка реквизитов 1с', 'заливка реквизитов 1С', '')
ИМЯ_ИСТОЧНИКА = 'Чеко: карточка компании, блок «Контактная информация»'


def ссылка(огрн: str) -> str:
    огрн = re.sub(r'\D', '', str(огрн or ''))
    return f'https://checko.ru/company/{огрн}/contacts' if огрн else ''


def main():
    db = EDB.EnrichDB()
    # ССЫЛКА НЕ УТРАЧЕНА — ОНА ЛЕЖИТ В enrich.db. Сборщик `checko_contacts.py`
    # писал КАЖДЫЙ номер строкой в `phone_contacts` с `source='checko:contacts'`
    # и `source_url` = тот самый адрес карточки, который он открыл. То же для
    # почт в `emails`. Потерял провенанс плоский столбец снимка панели
    # `telefony_checko`, а не источник. Поэтому сначала берём НАСТОЯЩИЙ адрес
    # оттуда и только если его нет — собираем из ОГРН.
    живая = {}
    for табл in ('phone_contacts', 'emails'):
        try:
            for и, у in db.cx.execute(
                    f"SELECT inn, source_url FROM {табл} "
                    f"WHERE COALESCE(source,'') LIKE 'checko%' "
                    f"AND COALESCE(source_url,'')<>''"):
                живая.setdefault(str(и), str(у))
        except Exception as ex:  # noqa: BLE001
            print(f'{табл}: {str(ex)[:70]}')
    print('живых ссылок из enrich.db:', len(живая))

    # ОГРН ИЩЕМ ТАМ ЖЕ, ГДЕ ЕГО ИСКАЛ САМ СБОРЩИК. Первый прогон нашёл ОГРН
    # только у 103 из 1 366 — потому что смотрел в одну таблицу. У
    # `checko_contacts.py` порядок был другой: enrich.db, затем индекс обзвона,
    # и карточка панели тоже знает ЕГРЮЛ (её заполняли реквизитами). Один
    # источник вместо трёх дал бы 1 263 «ссылку собрать не из чего» — то есть
    # признание утраты там, где данные на месте.
    #
    # ГЛАВНЫЙ ИСТОЧНИК ОГРН — ТАБЛИЦА `requisites`, а не `companies`. Именно из
    # `requisites.phones_checko` `zalit_rekvizity.py` и брал эти телефоны, и
    # ОГРН там стоит у ВСЕХ 1 366. Пока я смотрел в `companies`, выходило 103
    # из 1 366 и напрашивался вывод «ссылку собрать не из чего» — то есть я
    # чуть не записал признанной утратой то, что лежит в соседней колонке
    # того же файла. Искать надо там, откуда данные пришли.
    огрн = {}
    for i, о in db.cx.execute(
            "SELECT inn, ogrn FROM requisites WHERE COALESCE(ogrn,'')<>''"):
        огрн[str(i)] = str(о)
    стат_огрн = Counter({'requisites (оттуда и телефоны)': len(огрн)})
    n = 0
    for i, о in db.cx.execute(
            "SELECT inn, ogrn FROM companies WHERE COALESCE(ogrn,'')<>''"):
        if str(i) not in огрн:
            огрн[str(i)] = str(о)
            n += 1
    стат_огрн['companies (добавил)'] = n
    try:
        _идx = r'C:\sender\obzvon-index.db'
        ix = sqlite3.connect('file:%s?mode=ro' % _идx, uri=True, timeout=20)
        n = 0
        for i, о in ix.execute(
                "SELECT inn, ogrn FROM obzvon WHERE COALESCE(ogrn,'')<>''"):
            if str(i) not in огрн:
                огрн[str(i)] = str(о)
                n += 1
        стат_огрн['индекс обзвона (добавил)'] = n
        ix.close()
    except Exception as ex:  # noqa: BLE001
        стат_огрн['индекс обзвона: ' + str(ex)[:40]] = 0
    # ВЕДУЩИЙ НОЛЬ В ИНН. Индекс обзвона знает 161 734 ОГРН, а совпало всего 87
    # из 1 366 — потому что ИНН вроде `0245966232` там хранится числом и теряет
    # ноль. Держим второй ключ «без ведущих нулей»: сравнивать надо значение,
    # а не то, как его записали.
    без_нулей = {}
    for и, о in огрн.items():
        без_нулей.setdefault(str(и).lstrip('0'), о)

    цб = sqlite3.connect(ЦБ, timeout=30)
    _к = {r[1] for r in цб.execute('PRAGMA table_info(company)')}
    print('колонки company:', ' '.join(sorted(_к)))
    for имя in ('ogrn', 'egrul', 'ogrn_egrul', 'ogrn_ip', 'egrul_ogrn'):
        if имя in _к:
            n = 0
            for i, о in цб.execute(
                    f"SELECT inn, COALESCE({имя},'') FROM company "
                    f"WHERE COALESCE({имя},'')<>''"):
                if str(i) not in огрн and re.sub(r'\D', '', str(о)):
                    огрн[str(i)] = str(о)
                    n += 1
            стат_огрн[f'карточка панели, {имя} (добавил)'] = n
    print('где взят ОГРН:', json.dumps(dict(стат_огрн), ensure_ascii=False))
    столбцы = {r[1] for r in цб.execute('PRAGMA table_info(company)')}
    нужны = {'telefony_checko', 'pochty_checko', 'istochnik_rekvizitov'}
    нет = нужны - столбцы
    if нет:
        print('НЕТ КОЛОНОК:', sorted(нет))
        цб.close()
        return

    стат = Counter()
    правки = []
    for инн, тел, поч, ист in цб.execute(
            "SELECT inn, COALESCE(telefony_checko,''), COALESCE(pochty_checko,''), "
            "COALESCE(istochnik_rekvizitov,'') FROM company"):
        инн = str(инн)
        if not (тел.strip() or поч.strip()):
            continue
        стат['предприятий с контактами чеко'] += 1
        if ист.strip() not in СТАРОЕ:
            стат['  провенанс уже назван иначе — не трогаю'] += 1
            continue
        у = живая.get(инн, '')
        откуда = 'ссылка живая, из enrich.db'
        if not у:
            у = ссылка(огрн.get(инн) or без_нулей.get(инн.lstrip('0')) or '')
            откуда = 'ссылка собрана из ОГРН'
        новый = f'{ИМЯ_ИСТОЧНИКА} — {у}' if у else (
            f'{ИМЯ_ИСТОЧНИКА} (адрес карточки не сохранён)')
        стат['  ' + откуда if у else '  БЕЗ ссылки: адрес не сохранён'] += 1
        правки.append((новый, инн))

    print(json.dumps(dict(стат.most_common()), ensure_ascii=False, indent=1))
    if not ПРИМЕНИТЬ:
        print('СУХОЙ ПРОГОН. Пример:', правки[0] if правки else '—')
        цб.close()
        return

    # СЧИТАЕМ ИЗМЕНЁННЫЕ СТРОКИ, А НЕ ДЛИНУ СПИСКА ПРАВОК. Я уже отчитывался
    # «обновлено 1591», где 1591 было len(правки) — это намерение, а не итог.
    до = цб.total_changes
    цб.executemany(
        "UPDATE company SET istochnik_rekvizitov=? WHERE inn=?", правки)
    цб.commit()
    изменено = цб.total_changes - до
    # перечитываем базу, а не верим своему же UPDATE
    осталось = цб.execute(
        "SELECT COUNT(*) FROM company WHERE COALESCE(istochnik_rekvizitov,'') "
        "LIKE '%реквизитов 1с%' AND (COALESCE(telefony_checko,'')<>'' "
        "OR COALESCE(pochty_checko,'')<>'')").fetchone()[0]
    стало = цб.execute(
        "SELECT COUNT(*) FROM company WHERE COALESCE(istochnik_rekvizitov,'') "
        "LIKE 'Чеко:%'").fetchone()[0]
    цб.close()

    # ДУБЛЬ В ДОЛГОВЕЧНОЕ ХРАНИЛИЩЕ: снимок панели пересобирается, enrich.db нет
    в_enrich = 0
    есть = {r[1] for r in db.cx.execute('PRAGMA table_info(companies)')}
    if 'istochnik_rekvizitov' not in есть:
        try:
            db.cx.execute('ALTER TABLE companies ADD COLUMN istochnik_rekvizitov TEXT')
        except Exception as ex:  # noqa: BLE001
            print('enrich.db: колонку не добавить:', str(ex)[:80])
    try:
        до_e = db.cx.total_changes
        db.cx.executemany(
            "UPDATE companies SET istochnik_rekvizitov=? WHERE inn=?", правки)
        db.cx.commit()
        в_enrich = db.cx.total_changes - до_e
    except Exception as ex:  # noqa: BLE001
        print('enrich.db: не записалось:', str(ex)[:120])

    with io.open(ПОТОК, 'a', encoding='utf-8') as ф:
        ф.write(json.dumps({'ts': int(time.time()), 'izmeneno': изменено,
                            'v_enrich': в_enrich, 'obrazec': правки[0][0]},
                           ensure_ascii=False) + '\n')
        ф.flush()
        os.fsync(ф.fileno())

    print(f'ИЗМЕНЕНО строк в панели: {изменено}')
    print(f'ИЗМЕНЕНО строк в enrich.db: {в_enrich}')
    print(f'осталось со старым провенансом: {осталось}')
    print(f'теперь названо Чеко: {стало}')


if __name__ == '__main__':
    main()
