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
import sys
from collections import Counter

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

ЖУРНАЛ = r'C:\sender\server\dadata_celi.jsonl'
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
    for и, d in последний.items():
        ок = (d.get('okved') or '').strip()
        ст = (d.get('status') or '').strip()
        статусы[ст or 'пусто'] += 1
        if ок:
            с_оквэдом += 1
        if СУХОЙ:
            continue
        if ок:
            db.upsert_company(и, okved=ок)
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
        'статусы': статусы.most_common(),
        'НЕ_ACTIVE_записано_в_stage_log': неактив,
        'сухой': СУХОЙ,
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
