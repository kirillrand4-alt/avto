# -*- coding: utf-8 -*-
"""ОГРН для предприятий, где человек назван, а телефона нет ни одного.

Такие предприятия можно добрать через карточку checko, но её адрес строится
из ОГРН — а ОГРН у нас нигде не сохранён, хотя ЕГРЮЛ отдаёт его в каждом
ответе. Клиент dadata просто не забирал это поле; теперь забирает.

Оп спрашивает ЕГРЮЛ ровно по этим предприятиям, невзирая на журнал прошлых
запросов: журнал говорит «спрашивали», но тогда мы выбрасывали ОГРН, и
повторить придётся. Список короткий, счёт идёт на десятки запросов.

Пишет `ogrn` и официальное краткое имя через `upsert_company`, ход — в
`ogrn_dobor.jsonl`. По умолчанию СУХОЙ ПРОГОН.

Запуск: python ogrn_dlya_bez_telefona.py [--lim N] [--apply]
"""
import json
import os
import sys
import time

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB      # noqa: E402
import dadata_client as DD   # noqa: E402

ПРИМЕНИТЬ = '--apply' in sys.argv
ЛИМ = int(sys.argv[sys.argv.index('--lim') + 1]) if '--lim' in sys.argv else 200
ЖУРНАЛ = r'C:\sender\server\ogrn_dobor.jsonl'
ТЕХ = set(EDB.EnrichDB.TECH_ROLES)


def main():
    DD.TOKEN = os.environ.get('DADATA_TOKEN', '') or DD.TOKEN
    if not DD.TOKEN:
        raise SystemExit('нет DADATA_TOKEN в окружении раннера')
    db = EDB.EnrichDB()
    q = db.cx.execute
    сп = ','.join('?' * len(ТЕХ))
    с_тел = {r[0] for r in q('SELECT DISTINCT inn FROM phone_contacts')}
    есть_огрн = {r[0] for r in q(
        "SELECT inn FROM companies WHERE COALESCE(ogrn,'')<>''")}
    цели = []
    for и, in q(f'SELECT DISTINCT inn FROM people WHERE role IN ({сп})',
                tuple(ТЕХ)):
        if и not in с_тел and и not in есть_огрн:
            цели.append(и)
    пройдены = set()
    if os.path.exists(ЖУРНАЛ):
        for ln in open(ЖУРНАЛ, encoding='utf-8', errors='replace'):
            try:
                пройдены.add(json.loads(ln).get('inn'))
            except Exception:  # noqa: BLE001
                continue
    цели = [и for и in цели if и not in пройдены][:ЛИМ]
    print(f'предприятий с людьми, без телефона и без ОГРН: {len(цели)}; '
          f'режим: {"ПРИМЕНЕНИЕ" if ПРИМЕНИТЬ else "сухой"}', flush=True)
    if not цели:
        print('добирать нечего')
        return

    с_огрн = ошибок = 0
    начало = time.time()
    for i, инн in enumerate(цели, 1):
        if time.time() - начало > 900:
            print(f'бюджет вышел на {i} из {len(цели)}')
            break
        try:
            r = DD.lookup(инн)
        except Exception as e:  # noqa: BLE001
            ошибок += 1
            continue
        with open(ЖУРНАЛ, 'a', encoding='utf-8') as ж:
            ж.write(json.dumps(dict(r, inn=инн), ensure_ascii=False) + '\n')
            ж.flush()
            os.fsync(ж.fileno())
        if r.get('ogrn'):
            с_огрн += 1
            if ПРИМЕНИТЬ:
                db.upsert_company(инн, ogrn=str(r['ogrn']))
        if r.get('short_name') and ПРИМЕНИТЬ:
            db.upsert_company(инн, short_name=r['short_name'][:160])
    if ПРИМЕНИТЬ:
        db.cx.commit()
    в_базе = q("SELECT COUNT(*) FROM companies WHERE COALESCE(ogrn,'')<>''"
               ).fetchone()[0]
    print(json.dumps({'спрошено': min(len(цели), i), 'ОГРН получено': с_огрн,
                      'ошибок': ошибок, 'с_ОГРН_в_базе_всего': в_базе},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
