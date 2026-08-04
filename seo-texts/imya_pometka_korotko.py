# -*- coding: utf-8 -*-
"""Укоротить мои пометки о дублях имени: на карточке они читаются как отладочный мусор.

НАЙДЕНО ГЛАЗАМИ, А НЕ ЗАПРОСОМ. Владелец дал вход в панель и написал «каждый заходит в
админку и смотрит глазами 15 разных карточек». Я все 15 смотрел ЗАПРОСАМИ к базе — и потому
не увидел, во что превратилась моя же правка. Карточка АО «Аммоний» после неё:

    Еремеев Э.Ю.        главный инженер
      Источник: поиск-ЛПР-3с-песочница [запись того же человека: «Еремеев Э.Ю.» — это
                инициалы к «Еремеев Эдуард Юрьевич»]
    Имя не установлено  главный инженер
      Источник: поиск-ЛПР-3с-песочница [имя снято: первое слово «Подписал» — не фамилия;
                в подписи инициалы стоят перед фамилией («Подписал: ]

Счётчик по-прежнему говорит 17, все четыре записи Еремеева стоят отдельными людьми, а к ним
теперь добавлено моё объяснение — длинное, техническое и ОБРЕЗАННОЕ на середине фразы.
То есть правка не убрала путаницу, а добавила к ней шум в поле, которое продавец читает как
провенанс.

ЧТО ИЗ ЭТОГО СЛЕДУЕТ, КРОМЕ САМОЙ ПРАВКИ. Поле `source` — это адрес происхождения, а не место
для заметок разработчика. Объяснение нужно мне при разборе, продавцу нужно одно слово: тот же
это человек или другой. Разбор целиком остаётся в файле `VAZHNOE-3s-PORCHA-IMEN.csv`, где ему
и место.

Модуль заменяет длинную пометку короткой и человеческой, не трогая ни имени, ни источника:

    [запись того же человека: «Еремеев Э.Ю.» — это инициалы к «Еремеев Эдуард Юрьевич»]
        → [дубль: тот же человек, что «Еремеев Эдуард Юрьевич»]
    [имя снято: первое слово «Подписал» — не фамилия; в подписи инициалы стоят перед ...]
        → [имя не разобрано: в источнике на месте фамилии стояло служебное слово]

Запуск:
    python3 imya_pometka_korotko.py             # посчитать
    python3 imya_pometka_korotko.py --primenit  # применить
"""
import base64
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'server'))
import run_on_server as R  # noqa: E402

SCRIPT = r'''
# -*- coding: utf-8 -*-
import collections, json, os, re, sqlite3, sys

PRIMENIT = 'PRIMENIT' in sys.argv
# Кого дублирует — вынимаем из моей же длинной пометки, чтобы не считать заново.
DUBL = re.compile(r'\s*\[запись того же человека:[^\]]*?«([^»]+)»\s*\]', re.S)
DUBL_PADEZH = re.compile(r'\s*\[запись того же человека: «([^»]+)» против «([^»]+)»[^\]]*\]', re.S)
SNYATO = re.compile(r'\s*\[имя снято:[^\]]*\]?', re.S)

itog = {}
for baza, tabl in ((r'C:\seostat\data\centrifugal.db', 'person'),
                   (r'C:\sender\enrich.db', 'people')):
    if not os.path.exists(baza):
        itog[tabl] = 'базы нет'
        continue
    cx = sqlite3.connect(baza)
    sch = collections.Counter()
    pravki = []
    for rid, src in cx.execute(
            "select rowid, coalesce(source,'') from %s "
            "where coalesce(source,'') like '%%[запись того же%%' "
            "   or coalesce(source,'') like '%%[имя снято%%'" % tabl):
        novyy = src
        m = DUBL_PADEZH.search(novyy)
        if m:
            # Падеж: «Еремеева» против «Еремеев» — называем НОМИНАТИВ, он и есть человек.
            novyy = DUBL_PADEZH.sub(' [дубль: падежная форма фамилии «%s»]' % m.group(2), novyy)
            sch['падеж'] += 1
        else:
            m = DUBL.search(novyy)
            if m:
                novyy = DUBL.sub(' [дубль: тот же человек, что «%s»]' % m.group(1), novyy)
                sch['дубль'] += 1
        if SNYATO.search(novyy):
            novyy = SNYATO.sub(' [имя не разобрано: в источнике на месте фамилии стояло '
                               'служебное слово]', novyy)
            sch['имя снято'] += 1
        # Обрезанный хвост от прежней пометки: открытая скобка без закрывающей.
        if novyy.count('[') > novyy.count(']'):
            novyy = novyy[:novyy.rfind('[')].rstrip() + ' [пометка была обрезана, снята]'
            sch['обрезанный хвост'] += 1
        if novyy != src:
            pravki.append((novyy[:1000], rid))
    itog[tabl] = {'строк_с_моей_пометкой': len(pravki), 'по_видам': dict(sch)}
    if PRIMENIT and pravki:
        cx.executemany('update %s set source = ? where rowid = ?' % tabl, pravki)
        cx.commit()
        itog[tabl]['применено'] = True
        itog[tabl]['осталось_длинных'] = cx.execute(
            "select count(*) from %s where coalesce(source,'') like '%%в подписи инициалы%%' "
            "or coalesce(source,'') like '%%это инициалы к%%'" % tabl).fetchone()[0]
print('ИТОГ ' + json.dumps(itog, ensure_ascii=False))
'''


def main():
    R.submit('enrich_contacts', {'op': 'panel_file_put', 'files': [
        {'dest': r'C:\sender\_ops\3s_pometka_korotko.py',
         'b64': base64.b64encode(SCRIPT.encode()).decode()}]}, timeout=300)
    r = R.submit('enrich_contacts',
                 {'op': 'panel_py', 'script': r'C:\sender\_ops\3s_pometka_korotko.py',
                  'argv': ['PRIMENIT'] if '--primenit' in sys.argv else [], 'timeout': 900},
                 timeout=1200)
    d = r.get('data') or {}
    for s in (d.get('stdout_tail') or '').splitlines():
        if s.strip().startswith('ИТОГ '):
            print(json.dumps(json.loads(s.strip()[5:]), ensure_ascii=False, indent=1))
            return
    print('пусто:', (d.get('stderr_tail') or '')[-900:], file=sys.stderr)


if __name__ == '__main__':
    main()
