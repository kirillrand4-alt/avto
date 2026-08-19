# -*- coding: utf-8 -*-
r"""Ревизия: где вообще в базах лежат сайты — по ВСЕМ таблицам и столбцам.

Владелец спросил: «и сайты ты по всем столбцам смотрел? по всем 160к+».
Раньше я брал два места (enrich.companies.site и obzvon.sites) — этого мало,
чтобы отвечать «все». Скрипт не гадает по именам столбцов: он перебирает
каждую таблицу, каждый текстовый столбец, и считает, сколько строк похожи на
адрес сайта (домен или http). Плюс отдельно — сколько ИНН добавит столбец
сверх того, что уже стоит в очереди зенки/разобрано.
"""
import json
import os
import re
import sqlite3

BD = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
OBZVON = r'C:\sender\obzvon-index.db'
ОЧЕРЕДЬ = r'C:\sender\zenno\ochered.txt'

ССЫЛКА = re.compile(r'(https?://|www\.)', re.I)
ДОМЕН = re.compile(r'^[a-z0-9-]+(\.[a-z0-9-]+)*\.(ru|рф|com|net|org|su|by|kz|biz|info|pro|shop|store|online|site|ru\.com)$', re.I)
ПОЧТА = re.compile(r'@')


def похоже_на_сайт(v):
    s = str(v or '').strip()
    if not s or len(s) > 300 or ПОЧТА.search(s):
        return False
    if ССЫЛКА.search(s):
        return True
    return bool(ДОМЕН.match(s.strip('/').lower()))


def таблицы(c):
    return [r[0] for r in c.execute(
        "select name from sqlite_master where type='table' "
        "and name not like 'sqlite_%'")]


def столбцы(c, t):
    return [(r[1], (r[2] or '').upper()) for r in c.execute('pragma table_info("%s")' % t)]


def ревизия(путь, имя):
    if not os.path.exists(путь):
        return []
    c = sqlite3.connect('file:%s?mode=ro' % путь.replace('\\', '/'), uri=True)
    вышло = []
    for t in таблицы(c):
        колонки = столбцы(c, t)
        имена = [n for n, _ in колонки]
        инн_кол = 'inn' if 'inn' in имена else None
        try:
            всего = c.execute('select count(*) from "%s"' % t).fetchone()[0]
        except Exception:
            continue
        if not всего:
            continue
        for n, тип in колонки:
            if тип.startswith('INT') or тип.startswith('REAL'):
                continue
            if n == инн_кол:
                continue
            try:
                проба = c.execute(
                    'select "%s" from "%s" where coalesce("%s",\'\')<>\'\' limit 4000'
                    % (n, t, n)).fetchall()
            except Exception:
                continue
            if not проба:
                continue
            попаданий = sum(1 for (v,) in проба if похоже_на_сайт(v))
            # ещё смотрим внутри длинных строк (json/список)
            внутри = 0
            if попаданий < len(проба) * 0.2:
                for (v,) in проба:
                    s = str(v or '')
                    if len(s) > 20 and ССЫЛКА.search(s):
                        внутри += 1
            if попаданий < 5 and внутри < 5:
                continue
            вышло.append({
                'бд': имя, 'таблица': t, 'столбец': n, 'строк_в_таблице': всего,
                'из_пробы_4000': len(проба),
                'сайт_целиком': попаданий, 'ссылка_внутри': внутри,
                'пример': next((str(v)[:120] for (v,) in проба
                                if похоже_на_сайт(v) or ССЫЛКА.search(str(v or ''))), ''),
            })
    c.close()
    return вышло


def главное():
    итог = ревизия(BD, 'enrich') + ревизия(OBZVON, 'obzvon')
    в_очереди = set()
    if os.path.exists(ОЧЕРЕДЬ):
        with open(ОЧЕРЕДЬ, encoding='utf-8', errors='replace') as f:
            for s in f:
                ч = s.strip().split(';')
                if ч and ч[0].isdigit():
                    в_очереди.add(ч[0])
    print(json.dumps({'в_очереди_инн': len(в_очереди), 'находки': итог},
                     ensure_ascii=False, indent=1))


главное()
