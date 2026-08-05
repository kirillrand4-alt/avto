# -*- coding: utf-8 -*-
"""Как система решает, КТО НАШ КЛИЕНТ. Читаю правило целиком, а не пересказываю по памяти.

Владелец спросил прямо: хорошо ли я разобралась. Честный ответ — частично, и вот что
именно я знаю проверенным, а что нет.

ЗНАЮ (видела в живом коде):
  * `_CAPEX_KW` — предфильтр по заголовку, но только для regional/google/xmlriver-*;
  * `col_vk` фильтрует сам: только сообщества, не реклама, не репост, длина ≥60,
    капекс-слово ОБЯЗАТЕЛЬНО, минус-словарь мусора, не дайджест;
  * `extract_event` (claude-fable-5) — тут и решается «капекс или нет» и «какая компания»;
  * фильтр страны: только РФ;
  * `_src_confirms` — первоисточник должен подтвердить компанию.

НЕ ЗНАЮ и иду смотреть:
  * `division_of(okved)` → 'kc' | 'meyer' | 'kc+meyer' и точный маппинг владельца на 77
    кодов (`enrich_db.OKVED_DIRECTIONS`) — а ведь ЭТО и есть «кто наш клиент» по роду
    занятий, всё остальное только про повод;
  * `hotness` — чем считается и на что влияет;
  * как из сигнала получается ИНН (там и живёт ошибка тёзок);
  * как панель выбирает, кому слать.

И СРАЗУ СНИМАЮ СВОЙ ЖЕ ПРИБОР. Я предложила заслон «регион новости не сходится с адресом
юрлица И род занятий непромышленный». Он дал 244 строки, я прочитала их глазами:

    ИНН 7736050003  Газпром, СПб, ОКВЭД 46.71.4     новость: НПЗ на Сахалине
    ИНН 7721230290  ЕвроХим, Краснодарский край     новость: завод аммиака в Кингисеппе
    ИНН 7710373095  ТМК, ОКВЭД 64.20 «финансы»      новость: завод профлиста в Ижевске

Это не ошибки привязки. Это ХОЛДИНГИ: головное юрлицо зарегистрировано в одном месте,
завод строится в другом, а ОКВЭД у головной конторы управленческий или оптовый. Мой
заслон убил бы Газпром, ЕвроХим и ТМК.

И вторая моя ошибка, поменьше: поле ОКВЭД хранит СПИСОК кодов через «|», а я брала
первый. У Газпрома первый 46.71.4 (опт), а дальше в том же поле 06.10.3, 35.21 —
добыча газа и производство электроэнергии. «Непромышленный» получился из чтения одного
кода из одиннадцати.

Поэтому здесь я не заслон строю, а СМОТРЮ, как устроено настоящее правило.
"""
import inspect
import io
import json
import os
import re
import sqlite3
import sys

sys.path.insert(0, r'C:\sender\server')

print('=== 1. МАППИНГ ОКВЭД -> НАПРАВЛЕНИЕ (правило владельца)')
try:
    import enrich_db as EDB
    print('enrich_db.__file__ = %s' % EDB.__file__)
    m = getattr(EDB, 'OKVED_DIRECTIONS', None)
    if m is None:
        print('  OKVED_DIRECTIONS нет; что есть похожего: %s'
              % [n for n in dir(EDB) if 'OKVED' in n.upper() or 'DIRECT' in n.upper()])
    else:
        print('  кодов в маппинге: %d' % len(m))
        for k in sorted(m)[:90]:
            print('    %-10s %s' % (k, m[k]))
    for imya in ('division_for_okveds', 'division_of'):
        f = getattr(EDB, imya, None)
        if f:
            print('\n  --- %s' % imya)
            for l in inspect.getsource(f).split('\n')[:50]:
                print('   %s' % l[:160])
except Exception as e:  # noqa: BLE001
    print('  не вышло: %s: %s' % (type(e).__name__, str(e)[:160]))

print('\n\n=== 2. ЧТО ТАКОЕ hotness И КТО ЕГО СТАВИТ')
try:
    ish = io.open(r'C:\sender\server\news_scan.py', encoding='utf-8',
                  errors='replace').read().split('\n')
    for i, s in enumerate(ish):
        if 'hotness' in s:
            print('%5d| %s' % (i + 1, s.strip()[:150]))
except Exception as e:  # noqa: BLE001
    print('  %s' % e)

print('\n\n=== 3. КАК ИЗ НАЗВАНИЯ КОМПАНИИ ПОЛУЧАЕТСЯ ИНН (тут живёт ошибка тёзок)')
try:
    for i, s in enumerate(ish):
        if re.search(r'dadata|suggest|find_inn|company_to_inn|_inn_by_name', s, re.I):
            for j in range(max(0, i - 3), min(len(ish), i + 4)):
                print('%5d|%s %s' % (j + 1, '>' if j == i else ' ', ish[j].strip()[:150]))
            print('     |')
except Exception as e:  # noqa: BLE001
    print('  %s' % e)

print('\n\n=== 4. ОКВЭД ХРАНИТСЯ СПИСКОМ — проверяю на живой базе')
BAZA = r'C:\sender\enrich.db'
if os.path.exists(BAZA):
    cx = sqlite3.connect('file:%s?mode=ro' % BAZA.replace('\\', '/'), uri=True)
    tabl = [r[0] for r in cx.execute("select name from sqlite_master where type='table'")]
    for t in tabl:
        kol = [r[1] for r in cx.execute('pragma table_info(%s)' % t)]
        if any('okved' in k.lower() for k in kol):
            k = [x for x in kol if 'okved' in x.lower()][0]
            n = cx.execute('select count(*) from %s where %s is not null and %s<>""'
                           % (t, k, k)).fetchone()[0]
            mn = cx.execute('select count(*) from %s where %s like "%%|%%"'
                            % (t, k)).fetchone()[0]
            print('  %s.%s: заполнено %d, из них СПИСКОМ через | %d' % (t, k, n, mn))
            for (v,) in cx.execute('select %s from %s where %s like "%%|%%" limit 4'
                                   % (k, t, k)):
                print('     %s' % str(v)[:140])
    cx.close()

print('\nИТОГ ' + json.dumps({'смотрела': 'okved-направления, hotness, привязка ИНН'},
                             ensure_ascii=False))
