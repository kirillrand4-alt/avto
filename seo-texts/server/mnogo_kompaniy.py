# -*- coding: utf-8 -*-
r"""Домены, которые поиск отдаёт МНОГИМ разным компаниям, — самопополняемый список.

Владелец 20.08: «разберись подробно». Разбор отказов «домен занят другим ИНН»
по всему журналу поиска:

    находок в журнале      45 653
    отбито как «занято»    21 133  (46,3%)
    доменов в отказах       4 331

Из них 486 доменов поиск вернул ЧЕТЫРЁМ И БОЛЕЕ разным компаниям — за ними
3 760 списанных компаний. Это по построению не может быть сайтом одной фирмы:
sensus.kz отдан 94 компаниям, prodoctorov.ru — 74, perevozka24.com — 66,
web.archive.org — 64, дальше региональные порталы (tatarstan.ru, irkobl.ru),
реестры СРО, тендерные площадки и каталоги поставщиков.

Руками такой список не поддержать — он растёт с каждой тысячей запросов.
Поэтому строим его ИЗ ДАННЫХ: домен, отданный N+ разным ИНН, попадает в
таблицу и дальше считается площадкой. Правило самопополняемое и проверяемое:
рядом с доменом хранится, скольким компаниям он был отдан.

Порог 4, а не 2-3, намеренно: сайт группы компаний законно обслуживает две-три
дочки (sds-group.ru — 3, stroytransgaz.ru — 2), и запрещать такие нельзя.

    python mnogo_kompaniy.py             посчитать
    python mnogo_kompaniy.py --primenit  записать таблицу
"""
import json
import os
import sqlite3
import sys
import time

DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (r'C:\sender\server', DIR):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)
import ploshchadki as PL  # noqa: E402

ЛОГ = os.environ.get('POISK_LOG', r'C:\sender\poisk_saytov.jsonl')
BD = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
ПОРОГ = int(os.environ.get('MNOGO_POROG', '4'))
СХЕМА = """CREATE TABLE IF NOT EXISTS domeny_mnogo_kompaniy(
    domen TEXT PRIMARY KEY, kompaniy INTEGER, primer_inn TEXT, ts TEXT)"""


def собрать():
    """Домен -> множество ИНН, которым поиск его отдавал."""
    из = {}
    if not os.path.exists(ЛОГ):
        return из
    with open(ЛОГ, encoding='utf-8', errors='replace') as f:
        for стр in f:
            try:
                d = json.loads(стр)
            except Exception:  # noqa: BLE001
                continue
            сайт = d.get('site')
            инн = str(d.get('inn') or '')
            if not сайт or not инн:
                continue
            дом = PL.домен(сайт)
            if дом:
                из.setdefault(дом, set()).add(инн)
    return из


def главное(применять=False):
    домены = собрать()
    годные = [(д, и) for д, и in домены.items() if len(и) >= ПОРОГ]
    годные.sort(key=lambda x: -len(x[1]))
    свод = {'доменов_в_журнале': len(домены), 'порог': ПОРОГ,
            'многокомпанийных': len(годные),
            'компаний_за_ними': sum(len(и) for _д, и in годные),
            'уже_в_списке_площадок': sum(1 for д, _и in годные if PL.из_списка(д))}
    свод['топ'] = [{'домен': д, 'компаний': len(и),
                    'в_списке': bool(PL.из_списка(д))} for д, и in годные[:15]]
    if применять:
        c = sqlite3.connect(BD, timeout=60)
        c.execute('PRAGMA busy_timeout=30000')
        c.execute(СХЕМА)
        сейчас = time.strftime('%Y-%m-%dT%H:%M:%S')
        c.executemany(
            'INSERT INTO domeny_mnogo_kompaniy(domen,kompaniy,primer_inn,ts) '
            'VALUES(?,?,?,?) ON CONFLICT(domen) DO UPDATE SET '
            'kompaniy=excluded.kompaniy, ts=excluded.ts',
            [(д, len(и), sorted(и)[0], сейчас) for д, и in годные])
        c.commit()
        свод['записано'] = len(годные)
        c.close()
    print(json.dumps(свод, ensure_ascii=False, indent=1))
    print(json.dumps({'ИТОГ': {k: v for k, v in свод.items() if k != 'топ'}},
                     ensure_ascii=False))


if __name__ == '__main__':
    главное('--primenit' in sys.argv)
