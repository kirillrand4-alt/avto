# -*- coding: utf-8 -*-
"""SQLite lower() НЕ трогает кириллицу — и это молча ломало все мои фильтры по русским словам.

КАК ВСКРЫЛОСЬ. Восстановление ссылок сказало «образцов просмотрено 0» на запросе
`where lower(source) like '%егрюл%' and source_url <> ''`, хотя двумя запросами раньше я
своими глазами видела строки с source «ЕГРЮЛ/dadata» и ссылкой на egrul.nalog.ru. Разница
между запросами была одна: в том, который сработал, рядом стояло `or lower(source) like
'%dadata%'` — латиница. Она и находила.

Встроенный `lower()` в SQLite приводит к нижнему регистру ТОЛЬКО ASCII. «ЕГРЮЛ» после
lower() остаётся «ЕГРЮЛ», и шаблон '%егрюл%' не совпадает никогда. Ошибки при этом нет:
запрос отрабатывает и возвращает пусто — то есть выглядит как честный ноль.

ЧТО ЭТО ЗНАЧИТ ДЛЯ УЖЕ СДЕЛАННОГО. Я этим приёмом искала центробежные машины, скрытия,
среду — везде вида `lower(quote) like '%центробежн%'`. Там, где в тексте слово написано с
заглавной («Центробежный нагнетатель», «ЦЕНТРОБЕЖНЫЙ КОМПРЕССОР»), совпадения НЕ БЫЛО.
Здесь считаю, сколько именно потеряно, по каждому ключевому слову — прежде чем что-то
пересчитывать.
"""
import json
import sqlite3

cx = sqlite3.connect(r'C:\seostat\data\centrifugal.db')
o = {'проверка_lower': cx.execute("select lower('ЕГРЮЛ'), lower('ABC')").fetchone()}
SLOVA = ['центробежн', 'турбокомпрессор', 'воздуходувк', 'нагнетател', 'поршнев', 'егрюл']
poteri = {}
for w in SLOVA:
    cherez_lower = cx.execute(
        "select count(*) from fact where lower(coalesce(quote,'')) like ?",
        (f'%{w}%',)).fetchone()[0]
    # Честный регистронезависимый поиск: сравниваем в Python, а не в SQL.
    chestno = 0
    for (q,) in cx.execute("select coalesce(quote,'') from fact"):
        if w in q.lower():
            chestno += 1
    poteri[w] = {'нашёл_SQL_lower': cherez_lower, 'на_самом_деле': chestno,
                 'ПОТЕРЯНО': chestno - cherez_lower}
o['потери_по_словам'] = poteri
o['контактов_егрюл_SQL'] = cx.execute(
    "select count(*) from person where lower(coalesce(source,'')) like '%егрюл%'").fetchone()[0]
n = 0
for (s,) in cx.execute("select coalesce(source,'') from person"):
    if 'егрюл' in s.lower():
        n += 1
o['контактов_егрюл_честно'] = n
o['из_них_со_ссылкой'] = sum(
    1 for s, u in cx.execute("select coalesce(source,''), coalesce(source_url,'') from person")
    if 'егрюл' in s.lower() and u)
print(json.dumps(o, ensure_ascii=False, indent=1))
