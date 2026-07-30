# -*- coding: utf-8 -*-
"""ЕГРЮЛ через dadata по целям без контактов: руководитель, почта, телефон.

Не технический ЛПР — и это надо говорить прямо. Но точка входа: имя
руководителя плюс телефон приёмной уже дают разговор, а юрзначимая почта
обязательна для юрлиц с 2025 года, то есть она есть почти у всех и она живая.

Зачем отдельный оп, если `dadata_client.py` уже есть: тот отдаёт результат
JSON'ом в песочницу, а песочница при рестарте откатывается к снимку. Урок
25.07 — результат ЛЮБОГО серверного прогона пишется в серверное durable-
хранилище (`enrich.db` плюс jsonl с fsync), а не только в возвращаемый JSON.

Пишем через канонические писатели: `add_person` (роль руководителя канон
разберёт сам), `add_email`, `add_phone` — последний сам отсечёт реквизиты и
не уронит уже известную роль.

Запуск: python dadata_dlya_celey.py [--targets ФАЙЛ] [--lim N] [--dry]
"""
import json
import os
import sys
import time

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB      # noqa: E402
import dadata_client as DD   # noqa: E402

СУХОЙ = '--dry' in sys.argv
ЦЕЛИ = (sys.argv[sys.argv.index('--targets') + 1] if '--targets' in sys.argv
        else r'C:\seostat\drop\celi_bez_tehlpr.jsonl')
ЛИМ = int(sys.argv[sys.argv.index('--lim') + 1]) if '--lim' in sys.argv else 300
ЖУРНАЛ = r'C:\sender\server\dadata_celi.jsonl'
ИСТОЧНИК = 'ЕГРЮЛ/dadata'


def main():
    DD.TOKEN = os.environ.get('DADATA_TOKEN', '') or DD.TOKEN
    if not DD.TOKEN:
        raise SystemExit('нет DADATA_TOKEN в окружении раннера')
    if not os.path.exists(ЦЕЛИ):
        raise SystemExit(f'нет файла целей {ЦЕЛИ}')
    цели = []
    with open(ЦЕЛИ, encoding='utf-8') as ф:
        for строка in ф:
            try:
                цели.append(json.loads(строка))
            except Exception:  # noqa: BLE001
                continue
    цели = цели[:ЛИМ]
    print(f'целей: {len(цели)}')
    sys.stdout.flush()

    db = EDB.EnrichDB()
    q = db.cx.execute
    было_л = q('SELECT COUNT(*) FROM people').fetchone()[0]
    было_т = q('SELECT COUNT(*) FROM phone_contacts').fetchone()[0]
    было_п = q('SELECT COUNT(*) FROM emails').fetchone()[0]

    с_рук, с_почтой, с_тел, ошибок = 0, 0, 0, 0
    начало = time.time()
    for i, c in enumerate(цели, 1):
        if time.time() - начало > 1100:
            print(f'бюджет времени вышел на {i} из {len(цели)}')
            break
        инн = c['inn']
        try:
            r = DD.lookup(инн)
        except Exception as e:  # noqa: BLE001
            ошибок += 1
            if ошибок <= 5:
                print(f'  {инн}: {str(e)[:80]}')
            continue
        with open(ЖУРНАЛ, 'a', encoding='utf-8') as ж:
            ж.write(json.dumps(dict(r, inn=инн), ensure_ascii=False) + '\n')
            ж.flush()
            os.fsync(ж.fileno())
        if not СУХОЙ:
            if r.get('full_name'):
                db.upsert_company(инн, name=r['full_name'])
            if r.get('mgmt_name'):
                db.add_person(инн, r['mgmt_name'], post=r.get('mgmt_post') or 'руководитель',
                              source=ИСТОЧНИК)
                с_рук += 1
            for э in (r.get('emails') or [])[:3]:
                db.add_email(инн, э, source=ИСТОЧНИК)
            for т in (r.get('phones') or [])[:3]:
                db.add_phone(инн, т, source=ИСТОЧНИК)
        if r.get('emails'):
            с_почтой += 1
        if r.get('phones'):
            с_тел += 1
        if i % 25 == 0:
            print(f'  … {i}/{len(цели)}: руководителей {с_рук}, с почтой '
                  f'{с_почтой}, с телефоном {с_тел}, ошибок {ошибок}')
            sys.stdout.flush()

    стало_л = q('SELECT COUNT(*) FROM people').fetchone()[0]
    стало_т = q('SELECT COUNT(*) FROM phone_contacts').fetchone()[0]
    стало_п = q('SELECT COUNT(*) FROM emails').fetchone()[0]
    print()
    print('=== ИЗ БАЗЫ (не из счётчиков прогона) ===')
    print(f'  люди:     было {было_л} → стало {стало_л} (+{стало_л - было_л})')
    print(f'  телефоны: было {было_т} → стало {стало_т} (+{стало_т - было_т})')
    print(f'  почты:    было {было_п} → стало {стало_п} (+{стало_п - было_п})')
    сп = ','.join('?' * len(цели))
    инны = [c['inn'] for c in цели]
    ост = q(f'SELECT COUNT(*) FROM companies WHERE inn IN ({сп}) '
            'AND inn NOT IN (SELECT inn FROM phone_contacts)', инны).fetchone()[0]
    print(f'  целей БЕЗ телефона осталось: {ост} из {len(цели)}')
    print(f'целей {len(цели)}, руководителей {с_рук}, ошибок {ошибок}')


if __name__ == '__main__':
    main()
