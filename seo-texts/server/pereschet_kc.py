# -*- coding: utf-8 -*-
r"""Пересчёт разбора КЦ на уже собранных паспортах — без похода в интернет.

Владелец 19.08 прислал справку сессии паспортов и сказал: «паспорт не твой
классификатор заполняет? где ставить кц или нет, я для этого скинул». Да, мой:
`site_facts.razlozhit_energohozyaystvo`. Правки внесены туда, здесь — прогон по
базе: facts_json уже лежит в enrich.db, модель не нужна, деньги не тратятся.

    python pereschet_kc.py            посчитать, ничего не записывая
    python pereschet_kc.py --primenit переписать разбор_КЦ в базе
"""
import json
import os
import sqlite3
import sys
import time

DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (r'C:\sender\server', DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import site_facts as SF  # noqa: E402

BD = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')


def главное(применять=False):
    c = sqlite3.connect(BD, timeout=60)
    строки = c.execute("select inn, facts_json from site_facts "
                       "where coalesce(facts_json,'')<>''").fetchall()
    свод = {'паспортов': len(строки), 'было_да': 0, 'стало_да': 0,
            'стало_да_с_выводом': 0, 'прибавка': 0, 'разбор_отсутствовал': 0}
    примеры, записи = [], []
    for инн, сырьё in строки:
        try:
            ф = json.loads(сырьё)
        except Exception:  # noqa: BLE001
            continue
        старый = ф.get('разбор_КЦ') or {}
        if not старый:
            свод['разбор_отсутствовал'] += 1
        было = bool(старый.get('признак_КЦ'))
        новый = SF.razlozhit_energohozyaystvo(ф)
        свод['было_да'] += было
        свод['стало_да'] += bool(новый['признак_КЦ'])
        свод['стало_да_с_выводом'] += bool(новый['признак_КЦ_с_выводом'])
        if not было and новый['признак_КЦ_с_выводом']:
            свод['прибавка'] += 1
            if len(примеры) < 12:
                примеры.append({
                    'инн': str(инн),
                    'улика': (новый['воздух_точно'] or новый['воздух_вероятно'])[:2],
                    'откуда': 'прямая' if новый['воздух_точно'] else 'вывод',
                })
        if применять and новый != старый:
            ф['разбор_КЦ'] = новый
            записи.append((json.dumps(ф, ensure_ascii=False), инн))
    if применять and записи:
        # База живая: в неё пишут зенка-мост и обогащение, и одна большая
        # транзакция на 12 тысяч строк ложится на «database is locked».
        # Поэтому пачками по 200 с ожиданием и повтором — так пересчёт
        # проходит между чужими записями, а не воюет с ними.
        c.execute('PRAGMA busy_timeout=30000')
        сделано = 0
        for i in range(0, len(записи), 200):
            кусок = записи[i:i + 200]
            for попытка in range(6):
                try:
                    c.executemany('update site_facts set facts_json=? where inn=?', кусок)
                    c.commit()
                    сделано += len(кусок)
                    break
                except sqlite3.OperationalError as e:
                    if 'locked' not in str(e) and 'busy' not in str(e):
                        raise
                    time.sleep(2 * (попытка + 1))
            else:
                свод['не_записано_кусков'] = свод.get('не_записано_кусков', 0) + 1
        свод['переписано'] = сделано
    c.close()
    свод['примеры_прибавки'] = примеры
    свод['ts'] = time.strftime('%Y-%m-%dT%H:%M:%S')
    print(json.dumps(свод, ensure_ascii=False, indent=1))
    # итог печатаем ПОСЛЕДНИМ: раннер обрезает вывод по хвосту
    print(json.dumps({'argv': sys.argv[1:], 'применять': применять,
                      'переписано': свод.get('переписано', 0)},
                     ensure_ascii=False))


if __name__ == '__main__':
    главное('--primenit' in sys.argv)
