# -*- coding: utf-8 -*-
"""Перенести уже вынесенные приговоры в базу продаж, откуда их читает панель.

Владелец: «не установлено» — это не мусор, а незнание, и такие предприятия надо
уметь ВЫБРАТЬ, чтобы доузнавать. Значит приговор должен быть фильтром на
панели, а не строкой в моей базе.

Панель видит две базы: `centrifugal.db` (её пересобирает офлайн-сборщик, и
любая пометка там живёт до ближайшей сборки) и `centro_sales.db` (её не
пересобирают — там живут скрытия, назначения и результаты звонков). Приговор
кладём во ВТОРУЮ: он решение, а не данные источника, и переживать пересборку
обязан.

`enrich.db` панель не видит вовсе — она в другом каталоге и принадлежит
конвейеру, а не сайту. Поэтому перенос, а не чтение на лету.

Запуск: python sud_v_panel.py [--apply]
"""
import json
import os
import sqlite3
import sys
import time
from collections import Counter

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

ПР = os.getenv('CENTRO_SALES_DB') or r'C:\seostat\data\centro_sales.db'
ПРИМЕНИТЬ = '--apply' in sys.argv


def main():
    db = EDB.EnrichDB()
    try:
        строки = list(db.cx.execute(
            'SELECT inn, verdikt, uverennost, COALESCE(pochemu,\'\') '
            'FROM sud_centro WHERE COALESCE(verdikt,\'\')<>\'\''))
    except Exception as e:  # noqa: BLE001
        raise SystemExit(f'нет таблицы приговоров: {str(e)[:90]}')
    пр = sqlite3.connect(ПР, timeout=20)
    пр.execute('PRAGMA busy_timeout=20000')
    пр.execute('CREATE TABLE IF NOT EXISTS sud_verdikt('
               'inn TEXT PRIMARY KEY, verdikt TEXT, uverennost INTEGER, '
               'pochemu TEXT, ts TEXT)')
    было = пр.execute('SELECT COUNT(*) FROM sud_verdikt').fetchone()[0]
    в = Counter(r[1] for r in строки)
    print(json.dumps({'приговоров_в_enrich': len(строки),
                      'уже_в_базе_продаж': было,
                      'вердикты': в.most_common(),
                      'режим': 'ПРИМЕНЕНИЕ' if ПРИМЕНИТЬ else 'сухой (--apply)'},
                     ensure_ascii=False, indent=1))
    if not ПРИМЕНИТЬ:
        пр.close()
        print('\nсухой прогон. Повторить с --apply')
        return
    сейчас = time.strftime('%Y-%m-%dT%H:%M:%S')
    пр.executemany(
        'INSERT OR REPLACE INTO sud_verdikt(inn, verdikt, uverennost, pochemu, ts)'
        ' VALUES(?,?,?,?,?)',
        [(и, в_, у, (п or '')[:400], сейчас) for и, в_, у, п in строки])
    пр.commit()
    стало = пр.execute('SELECT COUNT(*) FROM sud_verdikt').fetchone()[0]
    пр.close()
    print(json.dumps({'в_базе_продаж_стало': стало}, ensure_ascii=False))


if __name__ == '__main__':
    main()
