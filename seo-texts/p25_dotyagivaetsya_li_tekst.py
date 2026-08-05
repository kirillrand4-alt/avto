# -*- coding: utf-8 -*-
"""Доезжает ли до классификатора ТЕКСТ статьи — или только заголовок. Моя же ошибка.

Я написала соседям: «классификатору уезжает только title». Это НЕВЕРНО, и вот живая
строка 1680 главного цикла:

    it = fetch_article(it)
    ev = extract_event(it.get('full_text') or it['title'], it.get('source', ''))

Текст статьи качается ПОСЛЕ дедупа и уезжает целиком; заголовок — это фолбэк, когда
`full_text` пуст. Значит вопрос не «почему не отдают текст», а **«доезжает ли текст»**.
И тогда «ноль событий» у zakupki объясняется иначе: если `zakupki.gov.ru` не отдаёт
страницу извещения роботу, `full_text` пуст, и модель получает

    «Электронный аукцион №0318300194226000355»

то есть номер без предмета — и честно отвечает «не капекс». Поломка та же по последствию,
но чинится в ДРУГОМ месте: не в промпте, а в докачке.

ЧТО МЕРЯЮ. Беру живые items четырёх источников, зову на них ЖИВОЙ `fetch_article` и
печатаю: сколько получили `full_text`, какой длины, и первые 400 знаков — глазами, потому
что «длина 812» ничего не говорит: 812 знаков могут быть страницей «включите JavaScript».

Провайдера не трогаю. `seen_news` не пишу.
"""
import io
import json
import re
import sys

sys.path.insert(0, r'C:\sender\server')
import news_scan as NS  # noqa: E402

print('news_scan.__file__ = %s' % NS.__file__)
ish = io.open(NS.__file__, encoding='utf-8', errors='replace').read().split('\n')

ZAKUPKI_KW = ['компрессорная установка', 'компрессор винтовой', 'генератор азота']


def kak_v_boyu_google():
    inds = list(NS.KC_INDUSTRIES) + list(NS.MEYER_INDUSTRIES)
    return ['%s %s' % (t, ind) for t in NS.TRIGGERS[:2] for ind in inds][:6]


ISTOCHNIKI = [
    ('zakupki', lambda: NS.col_zakupki(ZAKUPKI_KW, 14, 4)),
    ('frp', lambda: NS.col_frp(14, 4)),
    ('google', lambda: NS.col_google(kak_v_boyu_google(), 14, 4)),
]

itog = {}
for imya, zov in ISTOCHNIKI:
    print('\n' + '=' * 64)
    print('=== %s' % imya)
    try:
        items = (zov() or [])[:4]
    except Exception as e:  # noqa: BLE001
        print('   коллектор упал: %s' % str(e)[:140])
        itog[imya] = {'коллектор упал': type(e).__name__}
        continue
    dostali, dlin = 0, []
    for it in items:
        zag = str(it.get('title') or '')[:96]
        try:
            it2 = NS.fetch_article(dict(it))
        except Exception as e:  # noqa: BLE001
            print('\n   · %s\n     fetch_article УПАЛ: %s' % (zag, str(e)[:120]))
            continue
        ft = str(it2.get('full_text') or '')
        if ft.strip():
            dostali += 1
            dlin.append(len(ft))
        print('\n   · %s' % zag)
        print('     ссылка: %s' % str(it.get('link') or '')[:110])
        print('     full_text: %d знаков%s' % (len(ft), '' if ft else '   <- ПУСТО, поедет заголовок'))
        if ft:
            print('     начало: %s' % re.sub(r'\s+', ' ', ft)[:400])
        # что реально уедет в промпт
        poedet = ft or str(it.get('title') or '')
        print('     В ПРОМПТ УЕДЕТ (%d знаков): %s'
              % (len(poedet), re.sub(r'\s+', ' ', poedet)[:160]))
    itog[imya] = {'items': len(items), 'с текстом': dostali,
                  'длины': dlin[:6]}
    print('\n   ИТОГ по источнику: из %d items текст достали у %d' % (len(items), dostali))

# главный цикл целиком — печатаю ПОСЛЕДНИМ, потому что хвост раннера хранит конец
print('\n\n########## главный цикл, строки 1655-1700')
for i in range(1654, min(len(ish), 1700)):
    print('%5d| %s' % (i + 1, ish[i][:168]))

print('\n')
for k, v in itog.items():
    print('REC %-9s %s' % (k, json.dumps(v, ensure_ascii=False)))
print('ИТОГ ' + json.dumps(itog, ensure_ascii=False))
