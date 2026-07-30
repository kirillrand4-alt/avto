# -*- coding: utf-8 -*-
"""Люди Тендер.Про → enrich.db, с привязкой к ИНН и сверкой с базой обзвона.

Соседняя сессия собрала `tp-lica.csv`: 3184 контактных лица из карточек
закупок Тендер.Про, с разделением роли на техническую и снабжение. Колонка
`inn` в этом файле ПУСТАЯ, и я сначала записал это как «привязки нет, нужен
резолвер имён по базе обзвона».

Это было неверно, и проверка на данных заняла минуту: ИНН лежит в СОСЕДНЕМ
файле `tp-inn.csv` (`company_id;company;inn;kpp`), и join по `company_id`
резолвит 3087 строк из 3184 — 97%. Сопоставлять названия с базой обзвона надо
не для привязки, а только для остатка в пять компаний и для ответа на вопрос
владельца «кто из них может стать нашим клиентом».

Привязка тут структурная, а не эвристическая: `company_id` — идентификатор
площадки, ИНН взят с её же карточки компании. Это ровно тот случай, когда
рубеж fail-closed ничего не стоит: нет company_id в справочнике — строка не
пишется вовсе.

Что делает:
  * join tp-lica × tp-inn по company_id;
  * рубеж «это вообще человек» (ФИО, а не название отдела или компании);
  * склейка дублей: один человек фигурирует на десятках закупок;
  * запись через канонические писатели enrich_db (add_person / add_phone /
    add_email) — не своим SQL;
  * durable-дамп в tp_lica.jsonl с fsync ДО записи в базу;
  * сверка ИНН с базой обзвона: кто уже наш, кто новый, ОКВЭД и выручка;
  * отчёт СЧИТАЕТСЯ ИЗ БАЗЫ, а не из счётчиков прогона.

Запуск: python tp_lica_import.py [--dry]
"""
import csv
import io
import json
import os
import re
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB       # noqa: E402
import enrich_contacts as EC  # noqa: E402

СУХОЙ = '--dry' in sys.argv
ДРОП = r'C:\seostat\drop\drop-storage'
ЖУРНАЛ = r'C:\sender\server\tp_lica.jsonl'
ИСТОЧНИК = 'tender.pro'
# Человеческий маршрут SPA и проверяемый API-адрес той же карточки. На
# API-адресе живьём проверено, что там есть и ФИО, и должность, и домен
# почты — то есть ссылка действительно доказывает контакт, а не просто
# указывает на площадку.
СТР = 'https://www.tender.pro/#/tender/{}'
АПИ = 'https://www.tender.pro/api/tender/{}/view_public'

# ФИО: «Волков Максим Валерьевич», «Степанова Светлана», «Чикуров В.В.».
# Требуем кириллицу и минимум две части — иначе в людях оказываются отделы.
_ФИО = re.compile(
    r'^[А-ЯЁ][а-яё-]{1,24}\s+(?:[А-ЯЁ][а-яё]{1,24}|[А-ЯЁ]\.)\s*'
    r'(?:[А-ЯЁ][а-яё]{1,24}|[А-ЯЁ]\.)?\s*$')
# То, что человеком не является, но в поле контактного лица встречается.
_НЕ_ЧЕЛОВЕК = re.compile(
    r'\b(?:ооо|оао|пао|зао|ао|ип|фгуп|гуп|мup|муп|отдел|служба|управлен|'
    r'департамент|сектор|бюро|группа компаний|филиал|тендерн|закупк)\b', re.I)


def читать(имя):
    п = os.path.join(ДРОП, имя)
    if not os.path.exists(п):
        raise SystemExit(f'нет файла {п}')
    сыр = open(п, encoding='utf-8-sig', errors='replace').read()
    return list(csv.DictReader(io.StringIO(сыр), delimiter=';'))


def норм_фио(т):
    return re.sub(r'\s+', ' ', (т or '').strip())


def человек(имя):
    """Фильтр fail-closed: не похоже на ФИО — не пишем."""
    и = норм_фио(имя)
    if not и or len(и) < 5 or _НЕ_ЧЕЛОВЕК.search(и):
        return ''
    return и if _ФИО.match(и) else ''


def собрать():
    """{(инн, фио): карточка} — склеенные по человеку строки закупок."""
    справ = {r['company_id']: r['inn'].strip()
             for r in читать('tp-inn.csv') if (r.get('inn') or '').strip()}
    строк = 0
    без_инн = 0
    не_фио = 0
    люди = {}
    for r in читать('tp-lica.csv'):
        строк += 1
        инн = справ.get(r.get('company_id') or '')
        if not инн:
            без_инн += 1
            continue
        фио = человек(r.get('imya'))
        if not фио:
            не_фио += 1
            continue
        к = люди.setdefault((инн, фио), {
            'инн': инн, 'фио': фио, 'компания': (r.get('company') or '').strip(),
            'должности': [], 'телефоны': [], 'почты': [], 'роли': set(),
            'основания': [], 'тендеры': [], 'предметы': []})
        for поле, ключ in (('dolzhnost', 'должности'), ('telefon', 'телефоны'),
                           ('pochta', 'почты')):
            з = (r.get(поле) or '').strip()
            if з and з not in к[ключ]:
                к[ключ].append(з)
        # Площадка печатает должность не всегда, но ВСЕГДА печатает основание
        # контакта. Если должности нет, а роль техническая — основание и есть
        # всё, что мы знаем о человеке, и оно содержательно: «контактное лицо
        # по вопросам технического задания». Иначе 132 человека с телефонами
        # уходят в «общий».
        осн = (r.get('osnovanie') or '').strip()
        if осн and осн not in к['основания']:
            к['основания'].append(осн)
        к['роли'].add((r.get('rol') or '').strip())
        тид = (r.get('tender_id') or '').strip()
        if тид and тид not in к['тендеры']:
            к['тендеры'].append(тид)
            к['предметы'].append((r.get('predmet') or '').strip()[:300])
    return люди, {'строк': строк, 'без_инн': без_инн, 'не_фио': не_фио}


def лучшая_должность(к):
    """Самая информативная подпись: канон-роль важнее длины.

    Настоящая должность всегда бьёт основание контакта: «главный энергетик»
    конкретнее, чем «контактное лицо по техническим вопросам». Основание идёт
    в ход только когда должности нет вовсе.
    """
    лучш, лучш_роль = '', 'общий'
    for д in к['должности']:
        р = EDB.EnrichDB._canon_role(д)
        if р in EDB.EnrichDB.TECH_ROLES and лучш_роль not in EDB.EnrichDB.TECH_ROLES:
            лучш, лучш_роль = д, р
        elif not лучш or (р == лучш_роль and len(д) > len(лучш)):
            лучш, лучш_роль = д, р
    if лучш:
        return лучш, лучш_роль
    if 'техническая' in к['роли']:
        for о in sorted(к['основания'], key=len, reverse=True):
            if EDB.EnrichDB._canon_role(о) == 'техконтакт':
                return о[:160], 'техконтакт'
    return '', 'общий'


def main():
    люди, счёт = собрать()
    инны = sorted({к['инн'] for к in люди.values()})
    print(f'строк в выгрузке: {счёт["строк"]}, без резолва company_id: {счёт["без_инн"]}, '
          f'отсеяно рубежом ФИО: {счёт["не_фио"]}')
    print(f'людей после склейки: {len(люди)} в {len(инны)} компаниях')
    sys.stdout.flush()

    # durable ДО базы: если запись в базу упадёт, разбор не потерян
    if not СУХОЙ:
        with open(ЖУРНАЛ, 'a', encoding='utf-8') as ж:
            for к in люди.values():
                з = dict(к)
                з['роли'] = sorted(к['роли'])
                ж.write(json.dumps(з, ensure_ascii=False) + '\n')
            ж.flush()
            os.fsync(ж.fileno())
        print(f'журнал: {ЖУРНАЛ}')

    # сверка с базой обзвона — один проход по 679 МБ
    из_базы = EC._base_index(инны)
    print(f'из базы обзвона нашлось: {len(из_базы)} ИНН из {len(инны)}')
    sys.stdout.flush()

    db = EDB.EnrichDB()
    было = {}
    for имя, зпр in (('люди', 'SELECT COUNT(*) FROM people'),
                     ('телефоны', 'SELECT COUNT(*) FROM phone_contacts'),
                     ('почты', 'SELECT COUNT(*) FROM emails'),
                     ('компании', 'SELECT COUNT(*) FROM companies')):
        было[имя] = db.cx.execute(зпр).fetchone()[0]
    тех = "','".join(EDB.EnrichDB.TECH_ROLES)
    было['техЛПР'] = db.cx.execute(
        f"SELECT COUNT(*) FROM people WHERE role IN ('{тех}')").fetchone()[0]

    новых_компаний = 0
    if not СУХОЙ:
        for инн in инны:
            есть = db.cx.execute('SELECT inn FROM companies WHERE inn=?',
                                 (инн,)).fetchone()
            б = из_базы.get(инн) or {}
            имя = б.get('name') or next(
                (к['компания'] for к in люди.values() if к['инн'] == инн), '')
            if not есть:
                новых_компаний += 1
            поля = {'name': имя}
            # город из базы обзвона ложится в companies.region — колонки
            # `city` в таблице нет, и молча проглоченный kwarg оставил бы
            # поле пустым без единой ошибки
            for ключ, кол in (('site', 'site'), ('city', 'region'), ('okved', 'okved')):
                if б.get(ключ):
                    поля[кол] = б[ключ]
            try:
                db.upsert_company(инн, **поля)
            except Exception as e:  # noqa: BLE001
                print(f'  upsert {инн}: {e}')

        for к in люди.values():
            должность, роль = лучшая_должность(к)
            тид = к['тендеры'][0] if к['тендеры'] else ''
            урл = СТР.format(тид) if тид else ''
            db.add_person(к['инн'], к['фио'], post=должность,
                          phone=(к['телефоны'][0] if к['телефоны'] else ''),
                          email=(к['почты'][0] if к['почты'] else ''),
                          source=ИСТОЧНИК, source_url=урл)
            for т in к['телефоны']:
                db.add_phone(к['инн'], т, person=к['фио'], role=должность,
                             source=ИСТОЧНИК, source_url=урл)
            for п in к['почты']:
                db.add_email(к['инн'], п, role=должность, person=к['фио'],
                             source=ИСТОЧНИК, source_url=урл)

    стало = {}
    for имя, зпр in (('люди', 'SELECT COUNT(*) FROM people'),
                     ('телефоны', 'SELECT COUNT(*) FROM phone_contacts'),
                     ('почты', 'SELECT COUNT(*) FROM emails'),
                     ('компании', 'SELECT COUNT(*) FROM companies')):
        стало[имя] = db.cx.execute(зпр).fetchone()[0]
    стало['техЛПР'] = db.cx.execute(
        f"SELECT COUNT(*) FROM people WHERE role IN ('{тех}')").fetchone()[0]

    print()
    print('=== ИЗ БАЗЫ (не из счётчиков прогона) ===')
    for имя in ('компании', 'люди', 'техЛПР', 'телефоны', 'почты'):
        print(f'  {имя:<10} было {было[имя]:>6} → стало {стало[имя]:>6} '
              f'(+{стало[имя] - было[имя]})')
    print(f'  новых компаний в базе: {новых_компаний}')

    свои = db.cx.execute(
        f"SELECT COUNT(*) FROM people WHERE source='{ИСТОЧНИК}'").fetchone()[0]
    свои_тех = db.cx.execute(
        f"SELECT COUNT(*) FROM people WHERE source='{ИСТОЧНИК}' "
        f"AND role IN ('{тех}')").fetchone()[0]
    с_тел = db.cx.execute(
        f"SELECT COUNT(*) FROM people WHERE source='{ИСТОЧНИК}' "
        f"AND role IN ('{тех}') AND phone!=''").fetchone()[0]
    print(f'  людей источника {ИСТОЧНИК}: {свои}, технических {свои_тех}, '
          f'из них с телефоном {с_тел}')

    print()
    print('=== РОЛИ ЗАПИСАННЫХ ===')
    for роль, n in db.cx.execute(
            f"SELECT role, COUNT(*) FROM people WHERE source='{ИСТОЧНИК}' "
            'GROUP BY role ORDER BY 2 DESC').fetchall():
        м = 'ТЕХ' if роль in EDB.EnrichDB.TECH_ROLES else '   '
        print(f'  {м} {n:>4}  {роль}')

    print()
    print('=== МОБИЛЬНЫЕ У ТЕХНИЧЕСКИХ (что просил владелец) ===')
    моб = db.cx.execute(
        f"SELECT COUNT(*) FROM people WHERE source='{ИСТОЧНИК}' "
        f"AND role IN ('{тех}') AND (phone LIKE '%+7 9%' OR phone LIKE '%+79%' "
        "OR phone LIKE '%8-9%' OR phone LIKE '%(9%' OR phone LIKE '%89%')").fetchone()[0]
    print(f'  с похожим на мобильный: {моб}')
    for фио, пост, тел, урл in db.cx.execute(
            f"SELECT person,post,phone,source_url FROM people WHERE source='{ИСТОЧНИК}' "
            f"AND role IN ('{тех}') AND phone!='' ORDER BY post DESC LIMIT 12").fetchall():
        print(f'  {фио[:28]:<28} | {(пост or "")[:34]:<34} | {тел[:22]:<22} | {урл}')

    print()
    print('=== СВЕРКА С БАЗОЙ ОБЗВОНА ===')
    в_базе = [i for i in инны if i in из_базы]
    вне = [i for i in инны if i not in из_базы]
    print(f'  в базе обзвона: {len(в_базе)}, вне её: {len(вне)}')
    print('  ВНЕ базы обзвона (новые предприятия, кандидаты в базу):')
    for и in вне[:25]:
        имя = next((к['компания'] for к in люди.values() if к['инн'] == и), '')
        print(f'    {и}  {имя[:52]}')
    print(f'строк {счёт["строк"]}, людей {len(люди)}, компаний {len(инны)}')  # хвост для tail


if __name__ == '__main__':
    main()
