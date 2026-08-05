# -*- coding: utf-8 -*-
"""Найти ГОТОВЫЙ словарь ролей на 100+ должностей. Владелец говорит: он уже есть.

Владелец: «100+ ролей должно быть где-то прописано, это было уже готово, но текущие
опознавалки до этого использовались». Значит словарь существует, а живой канон
(`_ROLE_CANON`, ~16 ролей) его не знает — то есть работа сделана и не подключена.

Искать надо, а не угадывать. Прибор смотрит два места:

  1. ФАЙЛЫ: любые .py/.json/.csv/.txt/.md, где встречается список должностей.
     Признак — не слово «роль», а ПЛОТНОСТЬ должностей: сколько разных
     профессиональных слов (инженер, механик, энергетик, начальник, директор,
     мастер, технолог, метролог…) в файле. Список на 100+ должностей плотный,
     случайный текст — нет.
  2. ТАБЛИЦЫ во всех .db: колонки с именем про должность/роль, и сколько в них
     РАЗНЫХ значений.

Печатает найденное с числами. Ничего не меняет.
"""
import collections
import io
import json
import os
import re
import sqlite3

KORNI = (r'C:\sender', r'C:\seostat')
RASSH = ('.py', '.json', '.csv', '.txt', '.md', '.yaml', '.yml')
DOLZH = re.compile(
    r'инженер|механик|энергетик|технолог|метролог|начальник|директор|мастер|'
    r'снабжен|закупк|тендер|кипиа|асу|конструктор|прораб|бригадир|диспетчер|'
    r'главный|зам\.|заместител|руководител|специалист|техник|наладчик|слесар', re.I)
PROPUSK = re.compile(r'[\\/](?:node_modules|\.git|__pycache__|\.venv|dist|_bak)', re.I)


def plotnost(t):
    """Сколько РАЗНЫХ должностных слов и сколько строк на них похожи."""
    slova = set(x.lower() for x in DOLZH.findall(t))
    stroki = [s for s in t.split('\n') if DOLZH.search(s)]
    return len(slova), len(stroki)


nashli = []
seen = set()
for koren in KORNI:
    for put, papki, fayly in os.walk(koren):
        if PROPUSK.search(put + os.sep):
            papki[:] = []
            continue
        for f in fayly:
            if not f.lower().endswith(RASSH):
                continue
            p = os.path.join(put, f)
            if p in seen:
                continue
            seen.add(p)
            try:
                if os.path.getsize(p) > 6 * 1024 * 1024:
                    continue
                t = io.open(p, encoding='utf-8', errors='replace').read()
            except Exception:  # noqa: BLE001
                continue
            n_slov, n_strok = plotnost(t)
            if n_slov >= 8 and n_strok >= 40:
                nashli.append((n_strok, n_slov, p, os.path.getsize(p)))

nashli.sort(reverse=True)
print('=== ФАЙЛЫ, похожие на словарь должностей (по числу строк с должностями)')
for n_strok, n_slov, p, razm in nashli[:18]:
    print('  строк-с-должностями %-6d разных слов %-3d %8d б  %s'
          % (n_strok, n_slov, razm, p[-72:]))

print('\n=== ТАБЛИЦЫ БАЗ: колонки про должность и число РАЗНЫХ значений')
bazy = []
for koren in KORNI:
    for put, papki, fayly in os.walk(koren):
        if PROPUSK.search(put + os.sep):
            papki[:] = []
            continue
        for f in fayly:
            if f.lower().endswith(('.db', '.sqlite', '.sqlite3')):
                bazy.append(os.path.join(put, f))
itog = []
for b in bazy[:40]:
    try:
        cx = sqlite3.connect('file:%s?mode=ro' % b.replace('\\', '/'), uri=True)
        for (t,) in cx.execute("select name from sqlite_master where type='table'"):
            try:
                kol = [r[1] for r in cx.execute('pragma table_info(%s)' % t)]
            except Exception:  # noqa: BLE001
                continue
            for k in kol:
                if not re.search(r'role|rol\b|dolzh|должн|post|position|specialn', k, re.I):
                    continue
                try:
                    n = cx.execute('select count(distinct %s) from %s '
                                   'where coalesce(%s,"")<>""' % (k, t, k)).fetchone()[0]
                except Exception:  # noqa: BLE001
                    continue
                if n >= 20:
                    itog.append((n, os.path.basename(b), t, k))
        cx.close()
    except Exception:  # noqa: BLE001
        continue
itog.sort(reverse=True)
for n, b, t, k in itog[:20]:
    print('  разных значений %-6d  %s . %s . %s' % (n, b, t, k))

print('ИТОГ ' + json.dumps({'файлов-кандидатов': len(nashli),
                            'колонок-кандидатов': len(itog),
                            'лучший файл': nashli[0][2] if nashli else '',
                            'лучшая колонка': ('%s.%s.%s' % itog[0][1:]) if itog else ''},
                           ensure_ascii=False))
