# -*- coding: utf-8 -*-
r"""Добор событий из news_stream.jsonl в enrich.db.

Зачем. `_persist_event` в news_scan.py пишет событие в ДВА места: в jsonl с
fsync и в enrich.db. Запись в базу обёрнута в `except Exception: pass`, и когда
база занята другим писателем (16.09: `BEGIN IMMEDIATE` не проходит за 15 с,
«database is locked»), события молча остаются только в файле. Скан при этом
выглядит работающим — и он работает, просто половина результата не доезжает.

Этот скрипт доносит. Идемпотентен: событие считается уже донесённым, если в
signals есть строка с тем же ИНН и тем же source_url (а при пустом url — с тем
же ИНН и тем же началом текста). Резюмируемый: позиция последней разобранной
строки лежит в файле-отметке рядом с потоком, так что рестарт не начинает с нуля
и не плодит дублей.

Запуск:
    python dobor_signalov_iz_potoka.py [--proba] [--s-nachala]
        --proba      только посчитать, ничего не писать
        --s-nachala  игнорировать отметку и пройти весь поток заново
"""
import io
import json
import os
import sqlite3
import sys
import time

# Каталог сервера задан явно, а не по месту скрипта: раннер кладёт разовые
# скрипты в C:\sender\_tmp, и путь «рядом с собой» там указывает в пустоту.
DIR = os.environ.get('SENDER_SERVER_DIR') or r'C:\sender\server'
if not os.path.isdir(DIR):
    DIR = os.path.dirname(os.path.abspath(__file__))
ПОТОК = os.path.join(DIR, 'news_stream.jsonl')
ОТМЕТКА = os.path.join(DIR, 'news_stream.dobor-otmetka.json')
БАЗА = r'C:\sender\enrich.db'
ЖДАТЬ_БЛОКИРОВКУ = 900        # сколько секунд суммарно ждать занятую базу


def _соединение():
    c = sqlite3.connect(БАЗА, timeout=120)
    c.execute('pragma busy_timeout=120000')
    return c


def _ключ(d):
    return (str(d.get('inn') or ''), str(d.get('source_url') or ''))


def main():
    проба = '--proba' in sys.argv
    с_нуля = '--s-nachala' in sys.argv

    было = 0
    if not с_нуля and os.path.exists(ОТМЕТКА):
        try:
            было = int(json.load(open(ОТМЕТКА, encoding='utf-8')).get('строк', 0))
        except Exception:  # noqa: BLE001
            было = 0

    новые, строк = [], 0
    with io.open(ПОТОК, encoding='utf-8', errors='replace') as f:
        for s in f:
            строк += 1
            if строк <= было:
                continue
            try:
                d = json.loads(s)
            except Exception:  # noqa: BLE001
                continue
            if str(d.get('inn') or '').strip():
                новые.append(d)

    итог = {'строк_в_потоке': строк, 'было_разобрано': было,
            'новых_строк': строк - было, 'из_них_с_инн': len(новые)}

    if проба or not новые:
        итог['режим'] = 'проба' if проба else 'нечего доносить'
        print('===ИТОГ===')
        print(json.dumps(итог, ensure_ascii=False, indent=1))
        return 0

    # Ждём, пока база освободится: писать по одному в занятую базу бессмысленно.
    начало = time.time()
    while True:
        try:
            c = _соединение()
            c.execute('BEGIN IMMEDIATE')
            c.execute('ROLLBACK')
            c.close()
            break
        except sqlite3.OperationalError as e:
            if time.time() - начало > ЖДАТЬ_БЛОКИРОВКУ:
                итог['ОШИБКА'] = 'база занята %d с: %s' % (ЖДАТЬ_БЛОКИРОВКУ, repr(e)[:80])
                print('===ИТОГ===')
                print(json.dumps(итог, ensure_ascii=False, indent=1))
                return 1
            time.sleep(20)
    итог['ждали_базу_сек'] = int(time.time() - начало)

    sys.path.insert(0, DIR)
    import enrich_db as EDB
    db = EDB.EnrichDB()

    c = _соединение()
    уже = set()
    for inn, url in c.execute("select inn, coalesce(source_url,'') from signals"):
        уже.add((str(inn), str(url)))
    c.close()

    добавлено = пропущено = ошибок = 0
    for d in новые:
        k = _ключ(d)
        if k in уже:
            пропущено += 1
            continue
        try:
            db.upsert_company(k[0], name=d.get('company_full') or d.get('company'),
                              division=d.get('division'), okved=d.get('okved'),
                              region=d.get('dd_region') or d.get('region'))
            db.add_signal(k[0],
                          source=d.get('source_name') or d.get('collector') or 'news',
                          event_type=d.get('event_type') or '',
                          what=d.get('what') or '',
                          sum=str(d.get('sum') or ''),
                          source_url=d.get('source_url') or '',
                          hotness=int(d.get('hotness') or 0),
                          ts=d.get('published') or '')
            уже.add(k)
            добавлено += 1
        except Exception as e:  # noqa: BLE001
            ошибок += 1
            итог.setdefault('примеры_ошибок', [])
            if len(итог['примеры_ошибок']) < 3:
                итог['примеры_ошибок'].append(repr(e)[:120])

    with open(ОТМЕТКА, 'w', encoding='utf-8') as f:
        json.dump({'строк': строк, 'когда': time.strftime('%Y-%m-%d %H:%M:%S')}, f,
                  ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())

    c = _соединение()
    итог['сигналов_в_базе_теперь'] = c.execute('select count(*) from signals').fetchone()[0]
    c.close()
    итог.update({'добавлено': добавлено, 'уже_были': пропущено, 'ошибок': ошибок})
    print('===ИТОГ===')
    print(json.dumps(итог, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
