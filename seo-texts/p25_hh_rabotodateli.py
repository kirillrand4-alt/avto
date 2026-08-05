# -*- coding: utf-8 -*-
"""88 items — это НЕ 88 предприятий. Считаю работодателей, а не строки.

Починка col_hh дала 0 -> 88. Число крупное, значит проверяю прибор глазами, и глаза сразу
видят два подвоха в первых десяти строках:

    «Арм-Титан» повторён шесть раз подряд — один работодатель, шесть городов
    «Хохлов Максим ищет наладчика» — физлицо, а не предприятие

Считаю: сколько РАЗНЫХ работодателей, сколько строк на запрос, и сколько из запросов
вообще про нашу машину, а сколько про станки с ЧПУ (у них «пневматика» — это косвенно).
Провайдера и dadata не трогаю.
"""
import collections, json, re, sys
sys.path.insert(0, r'C:\sender\server')
import news_scan as NS

FIZLICO = re.compile(r'^[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+$')
NASHA = re.compile(r'компрессор|воздуходувн|воздухоразделен|энергетик', re.I)

po_zaprosu = collections.OrderedDict()
vse = []
for q in NS.HH_SIGNALS:
    try:
        it = NS.col_hh([q], '113', 14, 10) or []
    except Exception as e:
        it = []
        print('  %-44s УПАЛ %s' % (q[:44], str(e)[:60]))
    po_zaprosu[q] = it
    vse.extend(it)

rab = collections.Counter(str(i.get('company_hint') or '') for i in vse)
fiz = [r for r in rab if FIZLICO.match(r)]
print('\n=== ПО ЗАПРОСАМ (цель — 10 свежих с источника)')
for q, it in po_zaprosu.items():
    r = len(set(str(i.get('company_hint') or '') for i in it))
    print('  %-46s items %3d  разных работодателей %3d  %s'
          % (q[:46], len(it), r, 'НАША МАШИНА' if NASHA.search(q) else 'косвенный (ЧПУ и пр.)'))

print('\n=== ИТОГО')
print('  строк всего            %d' % len(vse))
print('  РАЗНЫХ работодателей   %d' % len(rab))
print('  похоже на физлицо      %d  %s' % (len(fiz), fiz[:6]))
print('  запросов про нашу машину %d из %d'
      % (sum(1 for q in NS.HH_SIGNALS if NASHA.search(q)), len(NS.HH_SIGNALS)))
print('\n=== ДЕСЯТЬ РАЗНЫХ РАБОТОДАТЕЛЕЙ ГЛАЗАМИ')
vidal = set()
for i in vse:
    c = str(i.get('company_hint') or '')
    if c in vidal: continue
    vidal.add(c)
    if len(vidal) > 10: break
    print('  · %-34s %s' % (c[:34], str(i.get('title') or '')[:96]))
print('\nИТОГ ' + json.dumps({'строк': len(vse), 'работодателей': len(rab),
                              'физлиц': len(fiz)}, ensure_ascii=False))
