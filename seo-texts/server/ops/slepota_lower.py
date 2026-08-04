# -*- coding: utf-8 -*-
"""Проверка находки 3-й сессии у СЕБЯ: SQL lower()/LIKE слеп к кириллице.

ЧТО НАШЛА СОСЕДКА. `sqlite3.lower('ЦЕНТРОБЕЖНЫЙ')` возвращает строку без
изменений, и `like '%центробежн%'` даёт ЛОЖЬ. У неё так молча пропало 8 957
строк, и один её отбор скрытий на пересмотр шёл по неполному списку.

ЕЁ ПРОСЬБА ВСЕМ: «проверьте у себя». Проверяю не глазами по коду, а замером:
для каждой пары (колонка, слово), которую мои опы реально спрашивают у базы,
считаю ДВА числа — как считает SQL и как считает Python. Разница и есть цена.

ГДЕ У МЕНЯ БЫЛО ОПАСНО, А ГДЕ НЕТ (проверяется здесь же, а не декларируется):
  * решения по среде принимает `sreda_primenit`, но он тянет цитату в Python и
    сравнивает регулярками `re.I` — питон кириллицу знает;
  * поиск продавца в панели идёт через `casefold()` (routes_centro_sales) и
    через UDF `panel_contains` (enrich_panel) — обе питоновские;
  * остаётся класс ОТЧЁТНЫХ чисел: `SELECT COUNT(*) ... LIKE '%слово%'`. Если
    такое число занижено, оно занижено и в том, что я говорил владельцу.

Запуск: python slepota_lower.py
"""
import json
import os
import sqlite3

БАЗЫ = [
    ('центробежка', r'C:\seostat\data\centrifugal.db'),
    ('P25', r'C:\seostat\data\p25.db'),
]

# (таблица, колонка, слово) — ровно то, что спрашивают мои опы
ПРОБЫ = [
    ('fact', 'quote', 'центробежн'),
    ('fact', 'quote', 'компрессор'),
    ('fact', 'quote', 'воздуходувк'),
    ('fact', 'quote', 'турбокомпрессор'),
    ('fact', 'medium', 'воздух'),
    ('fact', 'medium', 'газ'),
    ('fact', 'source', 'реестр ЭПБ'),
    ('person', 'position', 'главный инженер'),
    ('person', 'position', 'главный энергетик'),
    ('person', 'position', 'главный механик'),
    ('person', 'role', '4 круг'),
    ('contact', 'position', 'главный инженер'),
    ('contact', 'source', 'чеко'),
    ('company', 'name', 'завод'),
]


def есть(цб, табл, кол):
    try:
        return кол in {r[1] for r in цб.execute(f'PRAGMA table_info({табл})')}
    except sqlite3.Error:
        return False


def main():
    итог = []
    примеры = []
    for имя, путь in БАЗЫ:
        if not os.path.exists(путь):
            итог.append((имя, 'НЕТ ФАЙЛА', 0, 0, 0))
            continue
        цб = sqlite3.connect(f'file:{путь}?mode=ro', uri=True)
        for табл, кол, слово in ПРОБЫ:
            if not есть(цб, табл, кол):
                continue
            try:
                по_sql = цб.execute(
                    f"SELECT COUNT(*) FROM {табл} "
                    f"WHERE COALESCE({кол},'') LIKE ?", (f'%{слово}%',)).fetchone()[0]
                строки = [r[0] or '' for r in цб.execute(
                    f"SELECT COALESCE({кол},'') FROM {табл}")]
            except sqlite3.Error as ex:
                итог.append((имя, f'{табл}.{кол} ~ {слово}', -1, -1, -1))
                примеры.append(f'{имя} {табл}.{кол}: SQL-ошибка {str(ex)[:60]}')
                continue
            низ = слово.lower()
            по_python = sum(1 for з in строки if низ in з.lower())
            невидимо = по_python - по_sql
            итог.append((имя, f'{табл}.{кол} ~ {слово}', по_sql, по_python, невидимо))
            if невидимо > 0 and len(примеры) < 12:
                for з in строки:
                    if низ in з.lower() and низ not in з:
                        примеры.append(f'{имя} {табл}.{кол}: …{з[:110]}')
                        break
        цб.close()

    print('ПРИМЕРЫ НЕВИДИМЫХ СТРОК (SQL их не находит, Python находит):')
    for п in примеры:
        print('   ', п)
    if not примеры:
        print('    нет ни одной')

    print()
    print(f"{'база':12} {'проба':34} {'SQL':>7} {'правда':>7} {'невидимо':>9}")
    всего = 0
    for имя, проба, s, p, n in итог:
        if n:
            всего += max(n, 0)
        метка = '  <<<' if n else ''
        print(f'{имя:12} {проба:34} {s:7} {p:7} {n:9}{метка}')
    print()
    print(f'ИТОГО НЕВИДИМО ДЛЯ SQL ПО МОИМ ПРОБАМ: {всего}')


if __name__ == '__main__':
    main()
