# -*- coding: utf-8 -*-
"""Долить в базу панели людей и телефоны, которых продавец не видит.

Сверка показала: на сайте 1244 человека и 1441 телефон, а у нас по ТЕМ ЖЕ
предприятиям есть ещё 100 человек и 439 телефонов. База панели собрана
31.07 из моего же файла (это видно по колонке source), то есть она просто
отстала на всё, что влито позже: вложения ЕИС, второй обход сайтов, Тендер.Про.

Почему доливаем, а не ждём пересборки: пересборку делает офлайн-скрипт
соседней сессии, а продавцы звонят сегодня. Поэтому здесь два действия, и
второе важнее первого:
  1. дописать недостающее прямо в `centrifugal.db` — польза сейчас;
  2. выложить те же строки файлом на дроп — чтобы сборщик забрал их к себе
     и правка пережила пересборку. Без второго шага всё это исчезнет.

Дедуп по (ИНН, нормализованное ФИО) и по (ИНН, десять цифр номера): у одного
человека имя пишется по-разному, а номер — с разными разделителями.

По умолчанию СУХОЙ ПРОГОН. Запись — с --apply.
"""
import csv
import io
import os
import re
import shutil
import sqlite3
import sys
import time
import urllib.request

sys.path.insert(0, r'C:\seostat')
sys.path.insert(0, r'C:\sender\server')
from app.services import centro_catalog  # noqa: E402
import enrich_db as EDB  # noqa: E402

ПРИМЕНИТЬ = '--apply' in sys.argv
ДРОП = r'C:\seostat\drop\drop-storage'
_ДОБ = re.compile(r'\s*(?:доб|вн|внутр|ext)\.?\s*[:№]?\s*[\d\-]+\s*$', re.I)
_ТЕХ = None


def клч(т):
    return re.sub(r'\s+', ' ', str(т or '').strip().lower()).replace('ё', 'е')


def д10(т):
    ц = re.sub(r'\D', '', _ДОБ.sub('', str(т or '')))
    return ц[-10:] if len(ц) >= 10 else ''


def вид(ц):
    return 'нет номера' if not ц else ('мобильный' if ц.startswith('9')
                                       else 'городской')


def main():
    global _ТЕХ
    _ТЕХ = set(EDB.EnrichDB.TECH_ROLES) | {'техконтакт'}

    with centro_catalog.connect() as conn:
        инн_панели = {r[0] for r in conn.execute(
            'SELECT DISTINCT inn FROM company').fetchall()}
        есть_люди = {(r[0], клч(r[1])) for r in conn.execute(
            'SELECT inn, person FROM person').fetchall() if r[1]}
        есть_тел = set()
        for и, з in conn.execute(
                "SELECT inn, value FROM contact WHERE kind='phone'").fetchall():
            ц = д10(з)
            if ц:
                есть_тел.add((и, ц))
    print(f'на сайте: предприятий {len(инн_панели)}, людей {len(есть_люди)}, '
          f'телефонов {len(есть_тел)}')

    db = EDB.EnrichDB()
    q = db.cx.execute
    нов_люди, нов_тел = [], []
    видел_л, видел_т = set(есть_люди), set(есть_тел)

    for инн, фио, пост, роль, тел, поч, ист, урл in q(
            "SELECT inn, person, COALESCE(post,''), COALESCE(role,''), "
            "COALESCE(phone,''), COALESCE(email,''), COALESCE(source,''), "
            "COALESCE(source_url,'') FROM people").fetchall():
        if инн not in инн_панели or not фио:
            continue
        к = (инн, клч(фио))
        if к in видел_л:
            continue
        видел_л.add(к)
        ц = д10(тел)
        нов_люди.append((инн, фио, пост[:120], роль or 'роль не установлена',
                         тел or None, вид(ц), поч or None, урл or None,
                         (ист or 'enrich.db')[:120],
                         1 if роль in _ТЕХ else 0))

    # ЛЮДИ ИЗ ФАЙЛОВ, а не только из enrich.db. Первый прогон сказал «не
    # хватает 0» — и это была не хорошая новость, а взгляд не туда: сверка
    # считала недостачу по общей базе на дропе, а доливка читала enrich.db.
    # Люди с обхода сайтов и из вложений ЕИС живут только в выгрузках, в
    # enrich.db их нет вовсе. «Ноль расхождений» и «сравнил не те множества»
    # снаружи выглядят одинаково.
    путь_св = os.path.join(ДРОП, 'BAZA-CENTROBEZHNIKI-OBSHCHAYA.csv')
    из_файла = 0
    if os.path.exists(путь_св):
        csv.field_size_limit(10 ** 7)
        for r in csv.DictReader(io.StringIO(
                open(путь_св, encoding='utf-8-sig', errors='replace').read()),
                delimiter=';'):
            инн = (r.get('inn') or '').strip()
            фио = (r.get('fio') or '').strip()
            if not (инн in инн_панели and фио):
                continue
            к = (инн, клч(фио))
            if к in видел_л:
                continue
            видел_л.add(к)
            роль = (r.get('rol_kanon') or '').strip()
            ном = (r.get('mobilnyy_10cifr') or '').strip()
            тел = ('+7' + ном) if ном else (r.get('vse_nomera') or '').split(' | ')[0]
            ц = д10(тел)
            нов_люди.append((
                инн, фио, (r.get('dolzhnost') or '')[:120],
                роль or 'роль не установлена', тел or None, вид(ц),
                None, (r.get('ssylka_na_istochnik') or None),
                (r.get('istochnik') or 'общая база центробежных')[:120],
                1 if (роль in _ТЕХ or r.get('tehLPR') == 'да') else 0))
            из_файла += 1
    print(f'  из них добрано из общей базы на дропе: {из_файла}')

    for инн, тел, фио, роль, ист, урл in q(
            "SELECT inn, phone, COALESCE(person,''), COALESCE(role,''), "
            "COALESCE(source,''), COALESCE(source_url,'') "
            'FROM phone_contacts').fetchall():
        if инн not in инн_панели:
            continue
        ц = д10(тел)
        if not ц or (инн, ц) in видел_т:
            continue
        видел_т.add((инн, ц))
        техн = 1 if роль in _ТЕХ else 0
        нов_тел.append((инн, тел.strip(), 'phone', фио or None, роль or None,
                        None, вид(ц), (ист or 'enrich.db')[:120], урл or None,
                        0, техн, 1 if (фио or роль) else 0,
                        0 if фио else 1))

    print(f'НЕ ХВАТАЕТ на сайте: людей {len(нов_люди)}, телефонов {len(нов_тел)}')
    for с in нов_люди[:5]:
        print(f'  человек: {с[0]}  {с[1][:28]:<28} {с[3]:<14} {с[4] or "без номера"}')
    for с in нов_тел[:5]:
        print(f'  телефон: {с[0]}  {с[1][:20]:<20} {(с[3] or "владелец неизвестен")[:26]}')

    if not ПРИМЕНИТЬ:
        print('\nсухой прогон. Повторить с --apply')
        return
    if not (нов_люди or нов_тел):
        print('доливать нечего')
        return

    путь = str(centro_catalog.db_path())
    коп = путь + '.bak-' + str(int(time.time()))
    shutil.copy2(путь, коп)
    print(f'копия базы: {os.path.basename(коп)}')

    conn = sqlite3.connect(путь, timeout=30)
    try:
        conn.executemany(
            'INSERT INTO person (inn, person, position, role, phone, '
            'phone_type, email, source_url, source, is_tech) '
            'VALUES (?,?,?,?,?,?,?,?,?,?)', нов_люди)
        conn.executemany(
            'INSERT INTO contact (inn, value, kind, person, role, position, '
            'phone_type, source, source_url, is_purchaser, is_tech, has_role, '
            'is_unknown_owner) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)', нов_тел)
        conn.execute("INSERT OR REPLACE INTO import_info (key, value) "
                     "VALUES ('dolito_pervoy_sessiey', ?)",
                     (time.strftime('%Y-%m-%dT%H:%M:%S'),))
        conn.commit()
    finally:
        conn.close()

    # ЧИСЛА ПЕРЕЧИТЫВАНИЕМ БАЗЫ, И В ТЕХ ЖЕ ЕДИНИЦАХ, ЧТО ДО ДОЛИВКИ.
    # Первая версия печатала «до» парами (ИНН, десять цифр), а «после» —
    # строками таблицы, и доливка 35 номеров выглядела как +205: разницу дали
    # 170 дублей, которые лежали в contact ещё до нас. Ровно на этом мы за
    # сутки сгорели дважды («телефонов 4782» против «4612», «людей 445»
    # против «21»), поэтому здесь печатаются ОБА числа с подписью, что есть
    # что: пары — сколько разных номеров видит продавец, строки — сколько
    # записей лежит в базе.
    with centro_catalog.connect() as conn:
        л = conn.execute('SELECT COUNT(*) FROM person').fetchone()[0]
        т = conn.execute(
            "SELECT COUNT(*) FROM contact WHERE kind='phone'").fetchone()[0]
        тх = conn.execute(
            'SELECT COUNT(*) FROM person WHERE is_tech=1').fetchone()[0]
        пары_л = len({(r[0], клч(r[1])) for r in conn.execute(
            'SELECT inn, person FROM person').fetchall() if r[1]})
        пары_т = len({(r[0], д10(r[1])) for r in conn.execute(
            "SELECT inn, value FROM contact WHERE kind='phone'").fetchall()
            if д10(r[1])})
    print()
    print('=== ИЗ БАЗЫ ПАНЕЛИ ПОСЛЕ ДОЛИВКИ ===')
    print(f'  разных людей (ИНН+ФИО): {пары_л} (было {len(есть_люди)}, '
          f'долито {len(нов_люди)})')
    print(f'  разных номеров (ИНН+10 цифр): {пары_т} (было {len(есть_тел)}, '
          f'долито {len(нов_тел)})')
    print(f'  строк в таблицах: person {л}, contact-phone {т}; '
          f'технических людей {тх}')

    # ---- то же самое файлом для сборщика: без этого доливка умрёт
    имя = 'DOLIVKA-v-panel-ot-1-sessii.csv'
    п = os.path.join(r'C:\sender\server', имя)
    with open(п, 'w', encoding='utf-8-sig', newline='') as ф:
        в = csv.writer(ф, delimiter=';')
        в.writerow(['tip', 'inn', 'fio_ili_nomer', 'dolzhnost', 'rol',
                    'telefon', 'pochta', 'istochnik', 'ssylka', 'tehLPR'])
        for с in нов_люди:
            в.writerow(['человек', с[0], с[1], с[2], с[3], с[4] or '',
                        с[6] or '', с[8], с[7] or '', 'да' if с[9] else 'нет'])
        for с in нов_тел:
            в.writerow(['телефон', с[0], с[1], '', с[4] or '', с[1],
                        '', с[7], с[8] or '', 'да' if с[10] else 'нет'])
        ф.flush()
        os.fsync(ф.fileno())
    try:
        урл = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop')
        зпр = urllib.request.Request(
            урл.rstrip('/') + '/' + имя, data=open(п, 'rb').read(),
            method='PUT',
            headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
        urllib.request.urlopen(зпр, timeout=180).read()
        print(f'  для сборщика: {имя} на дропе')
    except Exception as e:  # noqa: BLE001
        print(f'  на дроп НЕ легло: {str(e)[:120]}')


if __name__ == '__main__':
    main()
