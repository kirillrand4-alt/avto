# -*- coding: utf-8 -*-
"""Заслон на ОБОЛОЧКУ в `fetch_article`. Приём 2-й сессии, применённый к стадии A.

ЧТО ЧИНЮ. Замер на живом сервере показал, что классификатор получает не статью:

    Google News   full_text 20 000 знаков — таблица стилей
                  «…body,html{height:100%;overflow:hidden}body{-webkit-font-smoothing…»
    ЕИС 44-ФЗ     full_text 19 999 знаков — рассказ портала о себе
                  «…Официальный сайт ЕИС предназначен для обеспечения свободного и
                    безвозмездного доступа к полной и достоверной информации…»

И это ХУЖЕ, чем «не скачалось»: в главном цикле стоит `full_text or title`, а фолбэк
срабатывает только на ПУСТОМ тексте. Текст не пуст — он полон мусора, поэтому заголовок
не спасает, и мы платим за 20 000 знаков оболочки на каждый item (~3,7 млн знаков за
прогон только по google).

ПРИЁМ БЕРУ У 2-й СЕССИИ, а не изобретаю: «страница считается прочитанной не по длине
текста, а по наличию содержимого, которое мы умеем назвать». У неё этот заслон уже
измерен на обходе ЕИС: 670 обходов, из них 412 — оболочка, записанная как успешный обход.
Её модулей в моей ветке нет, поэтому переношу правило, а не файл, и говорю об этом прямо.

ЗАМЕР ДО/ПОСЛЕ НА ОДНИХ И ТЕХ ЖЕ items — иначе это не починка, а надежда.
Правила чужого файла: бэкап, замена точной строки (совпадение обязано быть одно),
py_compile, откат при поломке синтаксиса.
"""
import importlib
import io
import json
import os
import py_compile
import re
import sys
import time

sys.path.insert(0, r'C:\sender\server')
import news_scan as NS  # noqa: E402

PUT = NS.__file__
print('живой файл: %s' % PUT)

ZAKUPKI_KW = ['компрессорная установка', 'генератор азота']


def kak_v_boyu_google():
    inds = list(NS.KC_INDUSTRIES) + list(NS.MEYER_INDUSTRIES)
    return ['%s %s' % (t, ind) for t in NS.TRIGGERS[:2] for ind in inds][:4]


# --- одни и те же items для обоих замеров --------------------------------------------
items = []
try:
    items += [dict(x) for x in (NS.col_google(kak_v_boyu_google(), 14, 3) or [])[:3]]
except Exception as e:  # noqa: BLE001
    print('google упал: %s' % str(e)[:120])
try:
    items += [dict(x) for x in (NS.col_zakupki(ZAKUPKI_KW, 14, 3) or [])[:3]]
except Exception as e:  # noqa: BLE001
    print('zakupki упал: %s' % str(e)[:120])
print('items для замера: %d' % len(items))

do = []
for it in items:
    try:
        r = NS.fetch_article(dict(it))
        do.append(len(str(r.get('full_text') or '')))
    except Exception:  # noqa: BLE001
        do.append(-1)

# --- правка ---------------------------------------------------------------------------
ish = io.open(PUT, encoding='utf-8').read()
STAROE = """    текст = _page_text(url)
    if текст:
        it['full_text'] = (str(it.get('title') or '') + '\\n\\n' + текст)[:FULLTEXT_CAP]"""
NOVOE = """    текст = _page_text(url)
    if текст and _pohozhe_na_obolochku(текст):
        # Оболочка сайта вместо статьи. Google News отдаёт таблицу стилей, карточка
        # 44-ФЗ — рассказ ЕИС о себе. Текст НЕ пуст, поэтому фолбэк `full_text or title`
        # ниже по циклу не срабатывает, и в провайдера уезжает 20 000 знаков мусора.
        # Приём 2-й сессии: страница прочитана не по длине, а по наличию содержимого,
        # которое мы умеем назвать.
        it['obolochka'] = 1
        текст = ''
    if текст:
        it['full_text'] = (str(it.get('title') or '') + '\\n\\n' + текст)[:FULLTEXT_CAP]"""

FUNKCIYA = '''
_OBOLOCHKA_PRIZNAKI = (
    re.compile(r'\\{[a-z-]{2,24}\\s*:[^}]{2,140}\\}'),          # таблица стилей в тексте
    re.compile(r'Официальный сайт Единой информационной системы', re.I),
    re.compile(r'включите\\s+JavaScript|enable\\s+JavaScript', re.I),
    re.compile(r'Your browser is out of date', re.I),
    re.compile(r'Личный кабинет 44-Ф3|Часто задаваемые вопросы\\s+Все разделы', re.I),
)


def _pohozhe_na_obolochku(t):
    """Оболочка сайта, а не статья. Смотрим ПЕРВЫЕ 2 000 знаков: у настоящей статьи там
    текст, у заглушки — стили или рассказ портала о себе."""
    golova = (t or '')[:2000]
    return any(p.search(golova) for p in _OBOLOCHKA_PRIZNAKI)


'''

print('\n=== ПРАВКА')
print('  искомый кусок в файле: %d раз' % ish.count(STAROE))
if '_pohozhe_na_obolochku' in ish:
    print('  УЖЕ ЕСТЬ — не трогаю')
elif ish.count(STAROE) != 1:
    print('  НЕ ПРАВЛЮ: совпадений не ровно одно')
elif ish.count('def fetch_article(it):') != 1:
    print('  НЕ ПРАВЛЮ: def fetch_article не ровно один')
else:
    bak = PUT + '.bak-3s-obol-%d' % int(time.time())
    io.open(bak, 'w', encoding='utf-8').write(ish)
    novyy = ish.replace('def fetch_article(it):', FUNKCIYA.lstrip('\n') + 'def fetch_article(it):')
    novyy = novyy.replace(STAROE, NOVOE)
    io.open(PUT, 'w', encoding='utf-8').write(novyy)
    try:
        py_compile.compile(PUT, doraise=True)
        print('  бэкап %s' % bak)
        print('  py_compile: синтаксис в порядке')
    except Exception as e:  # noqa: BLE001
        io.open(PUT, 'w', encoding='utf-8').write(ish)
        print('  СИНТАКСИС СЛОМАЛСЯ, откатила: %s' % str(e)[:200])

# --- замер ПОСЛЕ на ТЕХ ЖЕ items ------------------------------------------------------
importlib.reload(NS)
posle = []
for it in items:
    try:
        r = NS.fetch_article(dict(it))
        posle.append((len(str(r.get('full_text') or '')), bool(r.get('obolochka'))))
    except Exception as e:  # noqa: BLE001
        posle.append((-1, False))

print('\n\n########## ГЛАЗАМИ: что правка изменила, item за item')
sekonom = 0
for i, it in enumerate(items):
    d = do[i] if i < len(do) else -1
    p, ob = posle[i] if i < len(posle) else (-1, False)
    sekonom += max(0, d - p)
    print('\n  · [%s] %s' % (it.get('collector'), str(it.get('title') or '')[:96]))
    print('    %s' % str(it.get('link') or '')[:104])
    print('    было %6d знаков -> стало %6d %s'
          % (d, p, '(оболочка отсеяна, поедет заголовок)' if ob else ''))

print('\n\n########## ЧИСЛА')
print('  items                     %d' % len(items))
print('  оболочек отсеяно          %d' % sum(1 for x in posle if x[1]))
print('  знаков НЕ уехало в модель %d' % sekonom)
print('  в пересчёте на прогон google (~187 items): ~%d тыс. знаков'
      % (187 * (sekonom // max(1, len(items))) // 1000))
print('ИТОГ ' + json.dumps({'файл': PUT, 'items': len(items),
                            'оболочек': sum(1 for x in posle if x[1]),
                            'знаков сэкономлено': sekonom}, ensure_ascii=False))
