# -*- coding: utf-8 -*-
"""Заслон на оболочку ПЕРЕСТАРАЛСЯ. Глаза увидели то, чего счётчик показать не мог.

Первый заход отсеял 4 оболочки из 4, и число выглядело отличным. Но среди этих четырёх:

    Иной способ №32616266629 (223-ФЗ)   было 5 630 знаков -> стало 0

А эту самую страницу я час назад мерила отдельно, и там стояло **«НАЗВАН ЛИ ПРЕДМЕТ
ЗАКУПКИ: ДА»** — на ней есть «компрессор». Заслон выбросил единственный раздел ЕИС,
который отдаёт содержимое.

ПОЧЕМУ. Шапка «Официальный сайт Единой информационной системы…» стоит на ВСЕХ страницах
ЕИС, и хороших, и пустых. Признак шапки — признак сайта, а не признак пустоты.

ПОЧИНКА — то же правило, что я применяю к мере повода: **порядок и состав проверок**.
Оболочка = шапка есть И назвать в тексте НЕЧЕГО:

    шапка/стили в первых 2 000 знаках      И
    во ВСЁМ тексте нет ни нашей машины, ни капекс-слова
                                            -> оболочка, текст обнуляем
    шапка есть, но предмет назван           -> НЕ оболочка, текст оставляем

Замер снова на ТЕХ ЖЕ items, и снова с показом каждого глазами.
"""
import importlib
import io
import json
import py_compile
import re
import sys
import time

sys.path.insert(0, r'C:\sender\server')
import news_scan as NS  # noqa: E402

PUT = NS.__file__
ZAKUPKI_KW = ['компрессорная установка', 'генератор азота']


def kak_v_boyu_google():
    inds = list(NS.KC_INDUSTRIES) + list(NS.MEYER_INDUSTRIES)
    return ['%s %s' % (t, ind) for t in NS.TRIGGERS[:2] for ind in inds][:4]


items = []
for imya, zov in (('google', lambda: NS.col_google(kak_v_boyu_google(), 14, 3)),
                  ('zakupki', lambda: NS.col_zakupki(ZAKUPKI_KW, 14, 3))):
    try:
        items += [dict(x) for x in (zov() or [])[:3]]
    except Exception as e:  # noqa: BLE001
        print('%s упал: %s' % (imya, str(e)[:120]))

do = []
for it in items:
    r = NS.fetch_article(dict(it))
    do.append((len(str(r.get('full_text') or '')), bool(r.get('obolochka'))))

STARAYA = '''def _pohozhe_na_obolochku(t):
    """Оболочка сайта, а не статья. Смотрим ПЕРВЫЕ 2 000 знаков: у настоящей статьи там
    текст, у заглушки — стили или рассказ портала о себе."""
    golova = (t or '')[:2000]
    return any(p.search(golova) for p in _OBOLOCHKA_PRIZNAKI)'''

NOVAYA = '''_ESTЬ_CHTO_NAZVAT = re.compile(
    r'компрессор\\w*|турбокомпрессор\\w*|газодувк\\w+|воздуходувк\\w+|нагнетател\\w+|'
    r'воздухоразделен\\w+|\\bВРУ\\b|сжат\\w+\\s+воздух\\w*|пневмат\\w+|осушител\\w+|'
    r'генератор\\w*\\s+(?:азота|кислорода)|\\bазот\\w*\\b|\\bкислород\\w*\\b|\\bчиллер\\w*', re.I)


def _pohozhe_na_obolochku(t):
    """Оболочка сайта, а не статья.

    Шапка портала — признак САЙТА, а не признак пустоты: «Официальный сайт ЕИС…» стоит
    и на пустой карточке 44-ФЗ, и на содержательной 223-ФЗ, где предмет закупки назван.
    Поэтому оболочка = шапка есть И назвать в тексте нечего. Проверено глазами: первый
    вариант заслона выбросил страницу с «компрессором» вместе с пустыми.
    """
    t = t or ''
    golova = t[:2000]
    if not any(p.search(golova) for p in _OBOLOCHKA_PRIZNAKI):
        return False
    if _ESTЬ_CHTO_NAZVAT.search(t) or _CAPEX_KW.search(t):
        return False
    return True'''

ish = io.open(PUT, encoding='utf-8').read()
print('=== ПРАВКА')
print('  старая функция в файле: %d раз' % ish.count(STARAYA))
if '_ESTЬ_CHTO_NAZVAT' in ish:
    print('  уже поправлено — не трогаю')
elif ish.count(STARAYA) != 1:
    print('  НЕ ПРАВЛЮ: совпадений не ровно одно')
else:
    bak = PUT + '.bak-3s-obol2-%d' % int(time.time())
    io.open(bak, 'w', encoding='utf-8').write(ish)
    io.open(PUT, 'w', encoding='utf-8').write(ish.replace(STARAYA, NOVAYA))
    try:
        py_compile.compile(PUT, doraise=True)
        print('  бэкап %s\n  py_compile: в порядке' % bak)
    except Exception as e:  # noqa: BLE001
        io.open(PUT, 'w', encoding='utf-8').write(ish)
        print('  СИНТАКСИС СЛОМАЛСЯ, откатила: %s' % str(e)[:200])

importlib.reload(NS)
posle = []
for it in items:
    r = NS.fetch_article(dict(it))
    ft = str(r.get('full_text') or '')
    posle.append((len(ft), bool(r.get('obolochka')),
                  bool(re.search(r'компрессор|азот|кислород|осушител', ft, re.I))))

print('\n\n########## ГЛАЗАМИ, item за item')
for i, it in enumerate(items):
    d, dob = do[i]
    p, ob, est = posle[i]
    print('\n  · [%s] %s' % (it.get('collector'), str(it.get('title') or '')[:92]))
    print('    %s' % str(it.get('link') or '')[:104])
    print('    первый заслон: %6d знаков, оболочка=%s' % (d, dob))
    print('    второй заслон: %6d знаков, оболочка=%s, предмет назван=%s' % (p, ob, est))

print('\n\n########## ЧИСЛА')
print('  items                          %d' % len(items))
print('  отсеяно первым заслоном        %d' % sum(1 for x in do if x[1]))
print('  отсеяно вторым (правильным)    %d' % sum(1 for x in posle if x[1]))
print('  СПАСЕНО от ложного отсева      %d' % sum(1 for i in range(len(items))
                                                  if do[i][1] and not posle[i][1]))
print('ИТОГ ' + json.dumps({'items': len(items),
                            'первый отсеял': sum(1 for x in do if x[1]),
                            'второй отсеял': sum(1 for x in posle if x[1])},
                           ensure_ascii=False))
