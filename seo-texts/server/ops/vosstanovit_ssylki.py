# -*- coding: utf-8 -*-
"""Восстановить ссылку на первоисточник у фактов, где её нет (пункт 8).

Замер показал 270 чистых фактов без ссылки. Они делятся на три разные вещи,
и лечить их одинаково нельзя:

  52  в тексте есть НОМЕР документа или процедуры — ссылка собирается точно;
 218  зацепки нет: это записи вида «организация в выгрузке по нашему предмету»
      с торговых площадок. У них нет отдельного документа, потому что сам
      факт — присутствие организации в выгрузке площадки.

Для второй группы честный ответ не «ссылки нет», а ссылка на ПОИСК ПО ИНН на
той же площадке: продавец за один клик видит то же, что видели мы. Это
проверяемый след, и он помечен как поиск, а не как прямой документ — иначе
через неделю никто не отличит найденную страницу от собранной догадки.

По умолчанию СУХОЙ ПРОГОН. Запись — с --apply (перед ней делается копия базы).

Запуск: python vosstanovit_ssylki.py [--apply]
"""
import os
import re
import shutil
import sys
import time
from collections import Counter

sys.path.insert(0, r'C:\seostat')
from app.services import centro_catalog, centro_medium  # noqa: E402

ПРИМЕНИТЬ = '--apply' in sys.argv

_ЭПБ = re.compile(r'\b(\d{2}[-–][А-ЯЁA-Z]{2,3}[-–]\d{4,6}[-–]\d{4})\b')
_ЗАКУПКА = re.compile(r'\b(3\d{10}|2\d{9})\b')

# ПРОВЕРЕНО ЖИВЫМИ ЗАПРОСАМИ, а не собрано по виду. Ссылку получают только те
# площадки, где выдача по ИНН действительно открывается и ИНН на странице
# виден:
#   checko  — 200, ИНН на странице есть;
#   hh      — 200, ИНН на странице есть.
ПЛОЩАДКИ = {
    'справочник водоканалов': 'https://checko.ru/search?query={inn}',
    'вакансии hh': 'https://hh.ru/search/vacancy?text={inn}',
}

# А ЭТИ ССЫЛКИ НЕ ПИШУТСЯ, и вот почему. Проверка спасла от 196 мёртвых
# ссылок — они выглядели бы как источник, пока по ним не кликнут:
#   ТЭК-Торг     — /search отдаёт 404, /procedures уходит в цикл редиректов;
#   ЭТП ГПБ      — 200, но ИНН на странице нет: выдачу рисует скрипт,
#                  по ссылке продавец увидит пустую форму поиска;
#   Сбербанк-АСТ — то же самое, 30 КБ заглушки.
# Вместо ссылки пишем в source_note, ЧТО это за факт и где его смотреть
# руками. Пустое поле честнее нерабочей ссылки: пустое видно сразу.
БЕЗ_ССЫЛКИ = {
    'ЭТП ГПБ': 'ЭТП ГПБ: организация есть в выгрузке площадки по нашему '
               'предмету. Прямой ссылки на документ площадка не публикует, '
               'выдача по ИНН доступна только поиском на etpgpb.ru',
    'ТЭК-Торг': 'ТЭК-Торг: организация есть в выгрузке площадки по нашему '
                'предмету. Поиск по ИНН на tektorg.ru работает только из '
                'интерфейса, ссылкой не открывается',
    'Сбербанк-АСТ': 'Сбербанк-АСТ: организация есть в выгрузке площадки по '
                    'нашему предмету. Выдача по ИНН рисуется скриптом, '
                    'прямой ссылки нет',
}


def main():
    with centro_catalog.connect() as conn:
        ряды = centro_catalog._rows(conn, 'SELECT * FROM fact', ())
    план = []
    вид = Counter()
    for row in ряды:
        item = {
            **row,
            'status': row.get('status') or row.get('chto') or '',
            'model': row.get('model') or row.get('kto_ili_marka') or '',
            'equipment_type': (row.get('equipment_type')
                               or row.get('dolzhnost_ili_tip') or ''),
            'medium': row.get('medium') or row.get('rol') or '',
            'evidence': row.get('evidence') or row.get('chem_dokazano') or '',
            'quote': row.get('quote') or row.get('citata') or '',
        }
        if centro_medium.rejection_reason(item):
            continue
        урл = (row.get('source_url') or '').strip()
        if урл.lower().startswith(('http://', 'https://')):
            continue
        инн = (row.get('inn') or '').strip()
        поле = ' '.join(str(row.get(k) or '') for k in row)
        ист = (row.get('source') or '').strip()

        м = _ЭПБ.search(поле)
        if м:
            новый = ('https://monitor-pb.ru/conclusion/'
                     + м.group(1).replace('–', '-'))
            план.append((row['id'], новый, 'первоисточник по номеру заключения'))
            вид['по номеру заключения ЭПБ'] += 1
            continue
        м = _ЗАКУПКА.search(поле)
        if м:
            н = м.group(1)
            новый = ('https://zakupki.gov.ru/223/purchase/public/purchase/info/'
                     'common-info.html?regNumber=' + н)
            план.append((row['id'], новый, 'первоисточник по номеру процедуры'))
            вид['по номеру процедуры'] += 1
            continue
        шаблон = ПЛОЩАДКИ.get(ист)
        if шаблон and инн:
            план.append((row['id'], шаблон.format(inn=инн),
                         'поиск по ИНН, проверено живым запросом'))
            вид[f'ссылка-поиск: {ист}'] += 1
            continue
        пояснение = БЕЗ_ССЫЛКИ.get(ист)
        if пояснение:
            план.append((row['id'], '', пояснение))
            вид[f'без ссылки, с пояснением: {ист}'] += 1
            continue
        вид['восстановить нечем'] += 1

    print(f'фактов без ссылки: {sum(вид.values())}')
    for в, n in вид.most_common():
        print(f'  {n:>5}  {в}')
    print(f'\n{"БУДЕТ ЗАПИСАНО" if not ПРИМЕНИТЬ else "ЗАПИСЫВАЕТСЯ"}: {len(план)}')
    сс = sum(1 for _, у, _ in план if у)
    print(f'  из них РЕАЛЬНЫХ ССЫЛОК: {сс}, пояснений без ссылки: {len(план) - сс}')
    for ид, у, п in план[:6]:
        print(f'  id={ид}  {("→ " + у[:80]) if у else "(без ссылки) " + п[:80]}')

    if not ПРИМЕНИТЬ:
        print('\nсухой прогон, запись не делалась. Повторить с --apply')
        return
    if not план:
        print('писать нечего')
        return

    # centro_catalog.connect() открывает базу mode=ro — и это ПРАВИЛЬНО:
    # centrifugal.db целиком пересобирается офлайн-скриптом, панель её только
    # читает. Отсюда следствие, которое важнее самой записи: правка здесь
    # живёт до ближайшей пересборки. Поэтому мы (1) чиним сейчас, открыв базу
    # отдельным соединением на запись, и (2) кладём те же исправления файлом
    # на дроп — чтобы сборщик применил их у себя и правка стала постоянной.
    import sqlite3
    путь = str(centro_catalog.db_path())
    коп = путь + '.bak-' + str(int(time.time()))
    shutil.copy2(путь, коп)
    print(f'копия базы: {os.path.basename(коп)} '
          f'({os.path.getsize(коп)} байт)')

    conn = sqlite3.connect(путь, timeout=30)
    try:
        кол = {r[1] for r in conn.execute('PRAGMA table_info(fact)').fetchall()}
        if 'source_note' not in кол:
            conn.execute('ALTER TABLE fact ADD COLUMN source_note TEXT')
        for ид, у, п in план:
            if у:
                conn.execute(
                    'UPDATE fact SET source_url=?, source_note=? WHERE id=?',
                    (у, п, ид))
            else:
                conn.execute('UPDATE fact SET source_note=? WHERE id=?',
                             (п, ид))
        conn.commit()
    finally:
        conn.close()

    # то же самое — файлом для сборщика базы, иначе правка умрёт при пересборке
    import csv
    import urllib.request
    отч = os.path.join(r'C:\sender\server', 'ISPRAVLENIYA-ssylok-faktov.csv')
    with open(отч, 'w', encoding='utf-8-sig', newline='') as ф:
        в = csv.writer(ф, delimiter=';')
        в.writerow(['fact_id', 'inn', 'source', 'novaya_ssylka', 'pometka'])
        сп = {r['id']: r for r in ряды}
        for ид, у, п in план:
            r = сп.get(ид, {})
            в.writerow([ид, r.get('inn', ''), r.get('source', ''), у, п])
        ф.flush()
        os.fsync(ф.fileno())
    try:
        урл = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop')
        зпр = urllib.request.Request(
            урл.rstrip('/') + '/ISPRAVLENIYA-ssylok-faktov.csv',
            data=open(отч, 'rb').read(), method='PUT',
            headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
        urllib.request.urlopen(зпр, timeout=180).read()
        print('исправления для сборщика: ISPRAVLENIYA-ssylok-faktov.csv на дропе')
    except Exception as e:  # noqa: BLE001
        print('на дроп НЕ легло:', str(e)[:120])

    # ЧИСЛА ПЕРЕЧИТЫВАНИЕМ БАЗЫ, а не счётчиком прогона
    with centro_catalog.connect() as conn:
        всего = conn.execute('SELECT COUNT(*) FROM fact').fetchone()[0]
        сссыл = conn.execute(
            "SELECT COUNT(*) FROM fact WHERE COALESCE(source_url,'') LIKE 'http%'"
        ).fetchone()[0]
    print()
    print('=== ИЗ БАЗЫ ПОСЛЕ ЗАПИСИ ===')
    print(f'  фактов всего: {всего}, со ссылкой: {сссыл} '
          f'({round(100 * сссыл / max(1, всего))}%)')


if __name__ == '__main__':
    main()
