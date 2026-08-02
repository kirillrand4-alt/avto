# -*- coding: utf-8 -*-
"""Дозалить из журнала dadata то, что оп получил, но не записал: ОКВЭД и статус.

`dadata_dlya_celey` писал только `name`, руководителя, почты и телефоны. Почт
и телефонов ЕГРЮЛ на этом тарифе не отдаёт вовсе (замер: `emails`/`phones`
пусты во всех 2496 ответах), зато отдаёт два поля, которые мы выбрасывали:

  * `okved` — заполнен в 2494 из 2496. Это ровно то поле, из-за пустоты
    которого обход подразделений отсекал 252 цели с живым сайтом;
  * `status` — ACTIVE / LIQUIDATED / и т.п. Ликвидированное юрлицо в базе
    продажников это мусор в чистом виде: звонок туда не состоится никогда.

Повторно платить за уже сделанные запросы не надо — всё лежит в журнале.
Статус кладём в `stage_log` (там уникальность по паре ИНН+этап, то есть
перезапуск не плодит строк), ОКВЭД — штатным `upsert_company`.

Запуск: python dadata_dozalivka.py [--dry]
"""
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

ЖУРНАЛ = r'C:\sender\server\dadata_celi.jsonl'

# РЕГИОН ИЗ АДРЕСА. `upsert_company` регион принимает, а оп его не писал —
# хотя dadata отдаёт адрес всегда. Регион нужен не для красоты: им
# подтверждается привязка человека к предприятию, когда названия одинаковые
# («ООО Старт» в двух областях). У 89 отложенных строк графиков РТН регион
# компании неизвестен ровно поэтому.
_РЕГ_ГОРОД = re.compile(r'^\s*г\s+([А-ЯЁ][А-Яа-яЁё\-\s]{2,30})')
_РЕГ_ОБЛ = re.compile(
    r'^\s*([А-ЯЁ][А-Яа-яЁё\-\s]{2,40}?)\s+(обл|область|край|АО|'
    r'Респ|Республика|автономн\w*)\b')
_РЕГ_РЕСП = re.compile(r'^\s*(?:Респ|Республика)\s+([А-ЯЁ][А-Яа-яЁё\-\s]{2,30})')


def регион_из_адреса(адрес):
    """Первый элемент адреса ЕГРЮЛ — это субъект федерации либо город-субъект."""
    а = (адрес or '').strip()
    if not а:
        return ''
    первый = а.split(',')[0].strip()
    м = _РЕГ_РЕСП.match(первый)
    if м:
        return 'Республика ' + м.group(1).strip()
    м = _РЕГ_ОБЛ.match(первый)
    if м:
        хвост = м.group(2)
        конец = ' область' if хвост.startswith('обл') else (
            ' край' if хвост == 'край' else ' ' + хвост)
        return м.group(1).strip() + конец
    м = _РЕГ_ГОРОД.match(первый)
    if м:
        # город-субъект пишем как есть: «Москва», «Санкт-Петербург»
        return м.group(1).strip()
    return ''

СУХОЙ = '--dry' in sys.argv
ЭТАП = 'ЕГРЮЛ статус'


def main():
    if not os.path.exists(ЖУРНАЛ):
        raise SystemExit('журнала нет: ' + ЖУРНАЛ)
    последний = {}
    for ln in open(ЖУРНАЛ, encoding='utf-8', errors='replace'):
        try:
            d = json.loads(ln)
        except Exception:  # noqa: BLE001
            continue
        и = (d.get('inn') or '').strip()
        if и:
            последний[и] = d  # последняя запись побеждает

    db = EDB.EnrichDB()
    статусы = Counter()
    с_оквэдом = 0
    с_регионом = 0
    for и, d in последний.items():
        ок = (d.get('okved') or '').strip()
        ст = (d.get('status') or '').strip()
        статусы[ст or 'пусто'] += 1
        if ок:
            с_оквэдом += 1
        if СУХОЙ:
            continue
        рег = регион_из_адреса(d.get('address'))
        if рег:
            с_регионом += 1
        if ок or рег:
            поля = {}
            if ок:
                поля['okved'] = ок
            if рег:
                поля['region'] = рег
            db.upsert_company(и, **поля)
        if ст:
            db.cx.execute(
                'INSERT OR REPLACE INTO stage_log(inn,stage,detail,ts) '
                'VALUES(?,?,?,?)', (и, ЭТАП, ст, db.now))
    if not СУХОЙ:
        db.cx.commit()

    # числа — перечитыванием базы, не по счётчикам цикла
    q = db.cx.execute
    инны = list(последний)
    сп = ','.join('?' * len(инны))
    оквэд_в_базе = q(f"SELECT COUNT(*) FROM companies WHERE inn IN ({сп}) "
                     "AND COALESCE(okved,'')<>''", инны).fetchone()[0]
    неактив = q('SELECT COUNT(*) FROM stage_log WHERE stage=? '
                "AND detail<>'ACTIVE'", (ЭТАП,)).fetchone()[0]
    print(json.dumps({
        'в_журнале_уникальных_ИНН': len(последний),
        'с_ОКВЭДом_в_журнале': с_оквэдом,
        'с_ОКВЭДом_в_companies_после': оквэд_в_базе,
        'регион_разобран_из_адреса': с_регионом,
        'с_регионом_в_companies_после': q(
            f"SELECT COUNT(*) FROM companies WHERE inn IN ({сп}) "
            "AND COALESCE(region,'')<>''", инны).fetchone()[0],
        'статусы': статусы.most_common(),
        'НЕ_ACTIVE_записано_в_stage_log': неактив,
        'сухой': СУХОЙ,
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
