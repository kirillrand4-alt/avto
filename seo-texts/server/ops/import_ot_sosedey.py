# -*- coding: utf-8 -*-
"""Влить то, что соседние сессии выложили на дроп по нашим 1486 целям.

Два файла, и оба закрывают ровно те дыры, о которых я писал в отчёте:

  * `BEZ-TEHLPR-1486-dadata.csv` — ОФИЦИАЛЬНОЕ КРАТКОЕ наименование
    («ГУСП МТС "ЦЕНТРАЛЬНАЯ" РБ»). Именно им подписываются организации в
    государственных списках вроде графиков Ростехнадзора, а у нас в `name`
    лежит полная форма. Из полной краткая не выводится, когда это
    аббревиатура, — и сопоставление промахивалось. Плюс адрес, руководитель,
    ОКВЭД, статус.
  * `OBZVON-match-1486-3s.csv` — сопоставление наших целей с базой обзвона:
    телефоны, почты и сайты по 115 предприятиям.

Пишем ТОЛЬКО каноническими писателями (`add_phone`, `add_email`,
`upsert_company`): там стоят рубежи против реквизитов, принятых за телефон, и
там же канон роли. Источник помечаем явно — чтобы через неделю было видно, чьи
это данные и куда идти проверять.

Сайт из чужого файла кладём в `cand_site`, а НЕ в `site`: чужая привязка
домена нашим рубежом не проверена, а обходчик берёт только подтверждённое.

По умолчанию СУХОЙ ПРОГОН. Запуск: python import_ot_sosedey.py [--apply]
"""
import csv
import io
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

ДРОП = r'C:\seostat\drop\drop-storage'
ПРИМЕНИТЬ = '--apply' in sys.argv
ИСТ_ДАДАТА = 'ЕГРЮЛ (файл 3-й сессии)'
ИСТ_ОБЗВОН = 'база обзвона (файл 3-й сессии)'


def читать(имя):
    п = os.path.join(ДРОП, имя)
    if not os.path.exists(п):
        print(f'НЕТ файла {имя} — пропускаю')
        return []
    сырое = open(п, encoding='utf-8-sig', errors='replace').read()
    ряды = list(csv.DictReader(io.StringIO(сырое), delimiter=';'))
    if ряды and len(ряды[0]) <= 1:
        ряды = list(csv.DictReader(io.StringIO(сырое), delimiter=','))
    return ряды


def main():
    csv.field_size_limit(10 ** 7)
    db = EDB.EnrichDB()
    q = db.cx.execute
    было = {
        'кратких': q("SELECT COUNT(*) FROM companies "
                     "WHERE COALESCE(short_name,'')<>''").fetchone()[0],
        'телефонов': q('SELECT COUNT(*) FROM phone_contacts').fetchone()[0],
        'почт': q('SELECT COUNT(*) FROM emails').fetchone()[0],
        'кандидатов': q("SELECT COUNT(*) FROM companies "
                        "WHERE COALESCE(cand_site,'')<>'' "
                        "AND COALESCE(site,'')=''").fetchone()[0],
    }
    итог = Counter()

    # 1) ЕГРЮЛ-файл: краткое имя, адрес-регион, ОКВЭД, статус
    for r in читать('BEZ-TEHLPR-1486-dadata.csv'):
        инн = (r.get('inn') or '').strip()
        if not инн:
            continue
        кратк = (r.get('ofic_nazvanie') or '').strip()
        оквэд = (r.get('okved') or '').strip()
        поля = {}
        if кратк:
            поля['short_name'] = кратк[:160]
            итог['краткое имя'] += 1
        if оквэд:
            поля['okved'] = оквэд
        if поля and ПРИМЕНИТЬ:
            db.upsert_company(инн, **поля)
        ст = (r.get('status') or '').strip()
        if ст and ПРИМЕНИТЬ:
            db.cx.execute(
                'INSERT OR REPLACE INTO stage_log(inn,stage,detail,ts) '
                'VALUES(?,?,?,?)', (инн, 'ЕГРЮЛ статус', ст, db.now))
            итог['статус'] += 1

    # 2) файл обзвона: телефоны, почты, сайты
    for r in читать('OBZVON-match-1486-3s.csv'):
        инн = (r.get('inn') or '').strip()
        if not инн:
            continue
        for поле in ('phones_base', 'phones_site'):
            for т in re.split(r'[|,;]', r.get(поле) or ''):
                т = т.strip()
                # СЧЁТ ИДЁТ ВСЕГДА, запись — только при --apply. Иначе сухой
                # прогон показывает нули и выглядит как «в файле ничего нет»,
                # хотя там сто телефонов.
                if len(re.sub(r'\D', '', т)) >= 10:
                    итог['телефон найден'] += 1
                    if ПРИМЕНИТЬ and db.add_phone(инн, т, source=ИСТ_ОБЗВОН):
                        итог['телефон записан'] += 1
        for поле in ('emails_base', 'emails_site'):
            for э in re.split(r'[|,;\s]', r.get(поле) or ''):
                э = э.strip()
                if '@' in э and '.' in э.split('@')[-1]:
                    итог['почта найдена'] += 1
                    if ПРИМЕНИТЬ:
                        db.add_email(инн, э, source=ИСТ_ОБЗВОН)
        сайт = (r.get('sites') or '').split('|')[0].strip()
        if сайт:
            # ЧУЖАЯ привязка домена нашим рубежом не проверена — только кандидат
            есть = q("SELECT COALESCE(site,''),COALESCE(cand_site,'') "
                     'FROM companies WHERE inn=?', (инн,)).fetchone()
            if not есть or not есть[0].strip():
                итог['сайт-кандидат'] += 1
                if ПРИМЕНИТЬ:
                    db.upsert_company(инн, cand_site=сайт[:120])
        кратк = (r.get('name_short') or '').strip()
        if кратк and ПРИМЕНИТЬ:
            db.upsert_company(инн, short_name=кратк[:160])
        elif кратк:
            итог['краткое имя из обзвона'] += 1
    if ПРИМЕНИТЬ:
        db.cx.commit()

    стало = {
        'кратких': q("SELECT COUNT(*) FROM companies "
                     "WHERE COALESCE(short_name,'')<>''").fetchone()[0],
        'телефонов': q('SELECT COUNT(*) FROM phone_contacts').fetchone()[0],
        'почт': q('SELECT COUNT(*) FROM emails').fetchone()[0],
        'кандидатов': q("SELECT COUNT(*) FROM companies "
                        "WHERE COALESCE(cand_site,'')<>'' "
                        "AND COALESCE(site,'')=''").fetchone()[0],
    }
    print(json.dumps({
        'режим': 'ПРИМЕНЕНИЕ' if ПРИМЕНИТЬ else 'сухой (--apply)',
        'что_нашли': итог.most_common(),
        'ИЗ_БАЗЫ_было': было, 'ИЗ_БАЗЫ_стало': стало,
        'прирост': {к: стало[к] - было[к] for к in было},
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
