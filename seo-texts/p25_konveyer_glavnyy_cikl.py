# -*- coding: utf-8 -*-
"""Главный цикл news_scan: ЧТО именно уезжает классификатору. Второй заход, короче.

Первый заход напечатал слишком много, и хвост раннера (`stdout_tail` хранит КОНЕЦ) съел
начало — ровно то, ради чего заход и делался. Значит печатать надо мало и класть главное
ПОСЛЕДНИМ. Это не мелочь протокола: я уже теряла замер на том, что смотрела не тот кусок.

Что уже установлено первым заходом и подтверждено живым кодом:

    extract_event(title, source)   <- классификатору уезжает ТОЛЬКО title
    zakupki title = «Электронный аукцион №0318300194226000355»

В таком заголовке нет ни предмета закупки, ни компании — ничего, по чему можно решить
«капекс/не капекс». Предмет лежит в поле `query` того же item («компрессорная установка»),
и он в классификатор НЕ ПОПАДАЕТ. Если это подтвердится на главном цикле, то zakupki даёт
ноль не потому, что закупок нет, а потому что мы спрашиваем модель про номер аукциона.

Остаётся проверить ровно две вещи, и обе в главном цикле:
    1. правда ли зовётся `extract_event(it['title'], …)`, а не что-то, что склеивает поля;
    2. чем считается ключ дедупа — ссылкой или заголовком (от этого зависит, что значит
       «уже видели» для закупки, у которой заголовок это номер).
"""
import inspect
import io
import json
import re
import sys

sys.path.insert(0, r'C:\sender\server')
import news_scan as NS  # noqa: E402

ish = io.open(NS.__file__, encoding='utf-8', errors='replace').read().split('\n')


def pokazat(a, b, zag):
    print('\n\n########## %s   строки %d-%d' % (zag, a, b))
    for i in range(max(0, a - 1), min(len(ish), b)):
        print('%5d| %s' % (i + 1, ish[i][:168]))


# Порядок ОБРАТНЫЙ важности: главное печатается последним, потому что хвост хранит конец.
try:
    print('\n########## col_google')
    for l in inspect.getsource(NS.col_google).split('\n')[:60]:
        print('   %s' % l[:168])
except Exception as e:  # noqa: BLE001
    print('col_google: %s' % e)

try:
    print('\n########## col_zakupki')
    for l in inspect.getsource(NS.col_zakupki).split('\n')[:60]:
        print('   %s' % l[:168])
except Exception as e:  # noqa: BLE001
    print('col_zakupki: %s' % e)

pokazat(232, 262, '_news_key — чем меряется «уже видели»')

# Все места, где вообще зовётся extract_event — их может быть несколько
print('\n\n########## ВСЕ ЗОВЫ extract_event')
for i, s in enumerate(ish):
    if 'extract_event' in s:
        for j in range(max(0, i - 6), min(len(ish), i + 4)):
            print('%5d|%s %s' % (j + 1, '>' if j == i else ' ', ish[j][:168]))
        print('     |')

print('\nИТОГ ' + json.dumps({'файл': NS.__file__, 'строк': len(ish)}, ensure_ascii=False))
