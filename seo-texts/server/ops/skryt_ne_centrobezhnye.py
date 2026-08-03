# -*- coding: utf-8 -*-
"""Убрать из панели предприятия, у которых машина НЕ воздушная центробежная.

Прямое распоряжение владельца: «мусор не нужен, если это не воздушные
центробежные, убирай». Список не мой — его собрала соседняя сессия разбором
`tip_mashiny.py` с агентами-опровергателями и выложила файлами
`SVERKA-ubrat-iz-bazy.csv` (164) и `SVERKA-ubrat-iz-bazy-7.csv` (7).

Скрываем, а НЕ удаляем, и по трём причинам:
  * `centrifugal.db` read-only и пересобирается офлайн — удаление там не
    живёт дольше ближайшей сборки;
  * скрытое лежит в базе продаж с причиной и автором и возвращается одним
    нажатием: ошибиться может и сосед, и я;
  * причина пишется ПОИМЁННО из их же ярлыка, поэтому продавец, открыв
    «показать скрытые», видит не «убрано», а «вихревая или роторная
    воздуходувка, принцип не центробежный».

ЧТО ВАЖНО ЗНАТЬ ПРО ЭТОТ СПИСОК. Часть ярлыков означает «не центробежная», но
НЕ означает «не наша»: вихревая воздуходувка и Рутс — машины объёмные, а не
центробежные, при этом мы их продаём. Из ЭТОЙ панели они уходят правильно —
она про центробежные. Если по ним понадобится отдельная работа, все они
возвращаются по ИНН из журнала.

Почему тут голый sqlite3, а не `app.services.centro_sales`. Раннер запускает
скрипты питоном рассыльщика (`C:\Program Files\Python311`), а `centro_sales`
на первой же строке импортирует `bcrypt` — он стоит в окружении панели обзвона,
и здесь падает ImportError'ом до единой полезной строки. Тащить сюда bcrypt
ради вставки в таблицу — лишняя связность, поэтому пишем прямо в
`hidden_item` тем же запросом и той же схемой, что `hide_item`, включая
`INSERT OR REPLACE` и обрезку полей до 200 символов. Если схема там изменится,
изменить надо и здесь — это цена, и она названа.

По умолчанию СУХОЙ ПРОГОН. Запуск: python skryt_ne_centrobezhnye.py [--apply]
"""
import csv
import io
import json
import os
import re
import sqlite3
import sys
import time
from collections import Counter

ДРОП = r'C:\seostat\drop\drop-storage'
БАЗА_ЦБ = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
БАЗА_ПРОДАЖ = os.getenv('CENTRO_SALES_DB') or r'C:\seostat\data\centro_sales.db'
ПРИМЕНИТЬ = '--apply' in sys.argv
ФАЙЛЫ = ('SVERKA-ubrat-iz-bazy.csv', 'SVERKA-ubrat-iz-bazy-7.csv')
КТО = 'admin'

СХЕМА = """
CREATE TABLE IF NOT EXISTS hidden_item(
  id INTEGER PRIMARY KEY,
  inn TEXT NOT NULL,
  kind TEXT NOT NULL,
  value TEXT NOT NULL,
  reason TEXT,
  username TEXT,
  created_at TEXT,
  UNIQUE(inn, kind, value)
);
"""


def инн_ключ(v):
    return re.sub(r'\D', '', str(v or ''))[:12]


def скрытые(cx):
    cx.executescript(СХЕМА)
    return {str(r[0]) for r in
            cx.execute("SELECT inn FROM hidden_item WHERE kind='company'")}


def читать(имя):
    п = os.path.join(ДРОП, имя)
    if not os.path.exists(п):
        print(f'НЕТ файла {имя}')
        return []
    сыр = open(п, encoding='utf-8-sig', errors='replace').read()
    ряды = list(csv.DictReader(io.StringIO(сыр), delimiter=';'))
    if ряды and len(ряды[0]) <= 1:
        ряды = list(csv.DictReader(io.StringIO(сыр), delimiter=','))
    return ряды


def main():
    csv.field_size_limit(10 ** 7)
    цб = sqlite3.connect(f'file:{БАЗА_ЦБ}?mode=ro', uri=True, timeout=10)
    на_панели = {инн_ключ(r[0]) for r in цб.execute('SELECT inn FROM company')}
    цб.close()
    продажи = sqlite3.connect(БАЗА_ПРОДАЖ, timeout=10)
    продажи.execute('PRAGMA busy_timeout=10000')
    уже = скрытые(продажи)

    к_скрытию = {}
    ярлыки = Counter()
    для_справки = Counter()
    for имя in ФАЙЛЫ:
        for r in читать(имя):
            инн = инн_ключ(r.get('inn'))
            if not инн:
                continue
            ярлык = (r.get('moy_yarlyk') or '').strip() or 'не центробежная'
            для_справки[ярлык] += 1
            if инн not in на_панели:
                continue
            if инн in уже:
                continue
            к_скрытию[инн] = ярлык
            ярлыки[ярлык] += 1

    print(json.dumps({
        'в_файлах_сверки_строк': sum(для_справки.values()),
        'из_них_есть_на_панели_и_ещё_не_скрыты': len(к_скрытию),
        'ярлыки': ярлыки.most_common(12),
        'режим': 'ПРИМЕНЕНИЕ' if ПРИМЕНИТЬ else 'сухой (--apply)',
    }, ensure_ascii=False))

    if not ПРИМЕНИТЬ or not к_скрытию:
        return
    ошибок = 0
    сейчас = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    for инн, ярлык in к_скрытию.items():
        try:
            продажи.execute(
                'INSERT OR REPLACE INTO hidden_item'
                '(inn, kind, value, reason, username, created_at) '
                'VALUES(?,?,?,?,?,?)',
                (инн, 'company', инн,
                 f'не воздушная центробежная: {ярлык} (сверка 2-й сессии)'[:200],
                 КТО, сейчас))
        except Exception as e:  # noqa: BLE001
            ошибок += 1
            if ошибок <= 3:
                print(f'  {инн}: {str(e)[:80]}')
    продажи.commit()
    # число — ПЕРЕЧИТЫВАНИЕМ базы продаж, а не по счётчику цикла
    стало = скрытые(продажи)
    видно = sum(1 for и in на_панели if и not in стало)
    print(json.dumps({
        'скрыто_всего_в_базе_продаж': len(стало),
        'ошибок': ошибок,
        'предприятий_на_панели': len(на_панели),
        'останется_видимыми': видно,
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
