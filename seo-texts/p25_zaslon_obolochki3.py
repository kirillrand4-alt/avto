# -*- coding: utf-8 -*-
"""Третий заход: заслон качнуло в другую сторону. Убираю из спасательного условия капекс.

Ход правки, честно, все три шага:

    заслон 1  шапка портала в первых 2 000 знаках             -> отсеял 4 из 4
              и вместе с пустыми выбросил 223-ФЗ, где «компрессор» НАЗВАН
    заслон 2  шапка И (нет машины И нет капекс-слова)         -> отсеял 1 из 4
              спас 223-ФЗ, но вернул обратно ДВЕ карточки 44-ФЗ по 20 000 знаков
              рассказа портала: `_CAPEX_KW` широкий и цепляется за саму шапку ЕИС
    заслон 3  шапка И нет НАШЕЙ МАШИНЫ                        <- этот замер

Почему именно так. Спасать страницу должно только то, ради чего мы её качаем, — названная
машина или среда. Капекс-слово этого не даёт: «производство», «закупки», «предприятие»
стоят в подвале любого портала, и заслон превращается в решето.

Ожидание, которое проверяю (проба может провалиться):

    google, стили                       -> оболочка, отсеять
    ЕИС 44-ФЗ, машина не названа        -> оболочка, отсеять
    ЕИС 223-ФЗ, «компрессор» назван     -> НЕ оболочка, оставить

Замер на ТЕХ ЖЕ items, что и в двух прошлых заходах.
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
for zov in (lambda: NS.col_google(kak_v_boyu_google(), 14, 3),
            lambda: NS.col_zakupki(ZAKUPKI_KW, 14, 3)):
    try:
        items += [dict(x) for x in (zov() or [])[:3]]
    except Exception as e:  # noqa: BLE001
        print('коллектор упал: %s' % str(e)[:120])

do = []
for it in items:
    r = NS.fetch_article(dict(it))
    do.append((len(str(r.get('full_text') or '')), bool(r.get('obolochka'))))

STAROE = "    if _ESTЬ_CHTO_NAZVAT.search(t) or _CAPEX_KW.search(t):\n        return False"
NOVOE = ("    # Спасает страницу ТОЛЬКО названная машина или среда. Капекс-слово не годится:\n"
         "    # «производство», «закупки», «предприятие» стоят в подвале любого портала, и\n"
         "    # заслон становится решетом — проверено, две карточки 44-ФЗ по 20 000 знаков\n"
         "    # рассказа ЕИС о себе прошли обратно.\n"
         "    if _ESTЬ_CHTO_NAZVAT.search(t):\n        return False")

ish = io.open(PUT, encoding='utf-8').read()
print('=== ПРАВКА\n  искомое в файле: %d раз' % ish.count(STAROE))
if ish.count(STAROE) != 1:
    print('  НЕ ПРАВЛЮ: совпадений не ровно одно')
else:
    bak = PUT + '.bak-3s-obol3-%d' % int(time.time())
    io.open(bak, 'w', encoding='utf-8').write(ish)
    io.open(PUT, 'w', encoding='utf-8').write(ish.replace(STAROE, NOVOE))
    try:
        py_compile.compile(PUT, doraise=True)
        print('  бэкап %s\n  py_compile: в порядке' % bak)
    except Exception as e:  # noqa: BLE001
        io.open(PUT, 'w', encoding='utf-8').write(ish)
        print('  СИНТАКСИС СЛОМАЛСЯ, откатила: %s' % str(e)[:200])

importlib.reload(NS)
posle, provaly = [], []
for it in items:
    r = NS.fetch_article(dict(it))
    ft = str(r.get('full_text') or '')
    est = bool(re.search(r'компрессор|азот|кислород|осушител', ft, re.I))
    ob = bool(r.get('obolochka'))
    posle.append((len(ft), ob, est))
    kol = it.get('collector')
    link = str(it.get('link') or '')
    if kol == 'google' and not ob:
        provaly.append('google не отсеян: %s' % link[:70])
    if '/223/' in link and ob:
        provaly.append('223-ФЗ ОТСЕЯН ошибочно: %s' % link[:70])
    if '/ea20/' in link and not ob:
        provaly.append('44-ФЗ не отсеян: %s' % link[:70])

print('\n\n########## ГЛАЗАМИ, item за item')
for i, it in enumerate(items):
    print('\n  · [%s] %s' % (it.get('collector'), str(it.get('title') or '')[:90]))
    print('    %s' % str(it.get('link') or '')[:104])
    print('    заслон 2: %6d знаков, оболочка=%s' % do[i])
    print('    заслон 3: %6d знаков, оболочка=%s, машина в тексте=%s' % posle[i])

print('\n\n########## ПРОБА')
for p in provaly:
    print('  ПРОВАЛ: %s' % p)
print('  провалов %d' % len(provaly))
print('\n########## ЧИСЛА')
print('  items %d | отсеяно заслоном 2: %d | отсеяно заслоном 3: %d'
      % (len(items), sum(1 for x in do if x[1]), sum(1 for x in posle if x[1])))
sek = sum(max(0, 20000 - x[0]) for x in posle if x[1])
print('  знаков не уехало в модель на этих items: %d' % sek)
print('ИТОГ ' + json.dumps({'items': len(items), 'провалов': len(provaly),
                            'отсеяно': sum(1 for x in posle if x[1])}, ensure_ascii=False))
