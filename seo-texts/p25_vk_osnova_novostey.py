# -*- coding: utf-8 -*-
"""ВКонтакте — основа новостей. Владелец: «вк берёшь? оттуда основа новостей была».

Он прав числом: в базе 1 134 сигнала из ВК — больше, чем все прочие источники вместе.
Но прогон 12:31 дал из ВК ШЕСТЬ событий. Значит разбирать надо именно его, а я до сих пор
копала google/zakupki/frp, где объёма нет вовсе.

ЧЕМ ВК ОТЛИЧАЕТСЯ ОТ ОСТАЛЬНЫХ И ПОЧЕМУ ЭТО ВАЖНО:
  * у ВК `full_text` уже есть (текст поста) — значит болезнь «в провайдера уезжает
    оболочка сайта» его НЕ касается, качать нечего;
  * ВК НЕ проходит предфильтр `_CAPEX_KW` (строка 1272 перечисляет regional, google и
    xmlriver-*, ВК там нет) — значит за каждый пост платим вызовом провайдера;
  * у ВК своя защита `_src_confirms`: если пост даёт ссылку на первоисточник, статья по
    ней должна подтвердить компанию, иначе ссылка отбрасывается.

ЧТО МЕРЯЮ (без провайдера, seen_news только читаю):
  1. сколько постов отдаёт коллектор сейчас и сколько из них НОВЫХ (не в seen_news);
  2. есть ли у них full_text и какой длины — то есть будет ли модели что читать;
  3. сколько из новых прошли бы капекс-предфильтр, если бы он к ВК применялся —
     это прямая оценка, сколько вызовов провайдера тратится впустую;
  4. и печатаю посты глазами: счётчик не покажет, что текст это анонс концерта.

Плюс смотрю, что уже НАКОПЛЕНО в базе от ВК: какие группы дают прямые поводы, а какие
только шум. Источник, дающий 1 024 косвенных и 34 прямых, надо не выключать, а
переспрашивать по-другому.
"""
import collections
import inspect
import io
import json
import os
import re
import sqlite3
import sys

sys.path.insert(0, r'C:\sender\server')
import news_scan as NS  # noqa: E402

BAZA = r'C:\sender\enrich.db'
MASHINA = re.compile(
    r'компрессор\w*|турбокомпрессор\w*|газодувк\w+|газодувн\w+|воздуходувк\w+|'
    r'нагнетател\w+|воздухоразделен\w+|воздухоразделительн\w+|\bВРУ\b|'
    r'сжат\w+\s+воздух\w*|пневмат\w+|осушк\w+\s+возду\w+|'
    r'генератор\w*\s+(?:азота|кислорода)|\bазот\w*\b|\bкислород\w*\b|\bчиллер\w*', re.I)

print('news_scan.__file__ = %s' % NS.__file__)

# --- что уже накоплено от ВК ----------------------------------------------------------
if os.path.exists(BAZA):
    cx = sqlite3.connect('file:%s?mode=ro' % BAZA.replace('\\', '/'), uri=True)
    vsego = cx.execute("select count(*) from signals where source like '%онтакте%'"
                       " or source like '%vk%'").fetchone()[0]
    print('\n=== НАКОПЛЕНО: сигналов из ВК в базе: %d' % vsego)
    dlin = collections.Counter()
    pryamyh = 0
    for (w,) in cx.execute("select what from signals where source like '%онтакте%'"
                           " or source like '%vk%'"):
        n = len(w or '')
        dlin['до 40 знаков' if n < 40 else ('40-120' if n < 120 else 'больше 120')] += 1
        if MASHINA.search(w or ''):
            pryamyh += 1
    print('  длина what:  %s' % dict(dlin))
    print('  из них с названной нашей машиной: %d' % pryamyh)
    print('\n  --- 8 самых КОРОТКИХ what от ВК (глазами: это повод или огрызок?)')
    for w, u in cx.execute("select what, source_url from signals where (source like"
                           " '%онтакте%' or source like '%vk%') order by length(what)"
                           " limit 8"):
        print('    · %-70s %s' % (str(w)[:70], str(u or '')[:60]))
    cx.close()

# --- коллектор ------------------------------------------------------------------------
print('\n\n=== КОЛЛЕКТОР ВК: как он устроен')
kol = [n for n in dir(NS) if n.startswith('col_') and 'vk' in n.lower()]
print('  функции: %s' % kol)
for n in kol:
    try:
        s = inspect.getsource(getattr(NS, n))
        for l in s.split('\n')[:45]:
            print('   %s' % l[:160])
    except Exception as e:  # noqa: BLE001
        print('   %s: %s' % (n, e))

# флаг остановки, упомянутый в коде
for f in (r'C:\sender\server\vk_sweep_stop.flag', r'C:\sender\vk_sweep_stop.flag'):
    if os.path.exists(f):
        print('  ВНИМАНИЕ: есть флаг остановки %s' % f)

# --- живой зов ------------------------------------------------------------------------
print('\n\n=== ЖИВОЙ ЗОВ КОЛЛЕКТОРА ВК')
kluchi = set()
if os.path.exists(BAZA):
    cx = sqlite3.connect('file:%s?mode=ro' % BAZA.replace('\\', '/'), uri=True)
    try:
        kluchi = set(r[0] for r in cx.execute('select k from seen_news'))
    except Exception:  # noqa: BLE001
        pass
    cx.close()

items = []
for n in kol:
    f = getattr(NS, n)
    try:
        sig = inspect.signature(f)
        args = []
        for p in sig.parameters.values():
            if p.default is not inspect.Parameter.empty:
                continue
            args.append(14 if 'day' in p.name else (10 if 'max' in p.name else None))
        items = f(*args) or []
        print('  %s(%s) -> items %d' % (n, args, len(items)))
        break
    except Exception as e:  # noqa: BLE001
        print('  %s упал: %s: %s' % (n, type(e).__name__, str(e)[:140]))

novye, s_tekstom, kapeks, mash = [], 0, 0, 0
vidal = set()
for it in items:
    try:
        k = NS._news_key(it)
    except Exception:  # noqa: BLE001
        k = None
    if not k or k in vidal:
        continue
    vidal.add(k)
    if k in kluchi:
        continue
    novye.append(it)
    ft = str(it.get('full_text') or '')
    if ft.strip():
        s_tekstom += 1
    t = (str(it.get('title') or '') + ' ' + ft)
    if NS._CAPEX_KW.search(t):
        kapeks += 1
    if MASHINA.search(t):
        mash += 1

print('\n  сырых %d, уникальных %d, НОВЫХ %d' % (len(items), len(vidal), len(novye)))
print('  из новых: с текстом поста %d, прошли бы капекс-предфильтр %d, '
      'наша машина названа %d' % (s_tekstom, kapeks, mash))
print('  -> вызовов провайдера впустую (новые БЕЗ капекс-слова): %d из %d'
      % (len(novye) - kapeks, len(novye)))

print('\n  --- 10 НОВЫХ ПОСТОВ ГЛАЗАМИ')
for it in novye[:10]:
    ft = re.sub(r'\s+', ' ', str(it.get('full_text') or ''))
    print('\n    · %s' % str(it.get('title') or '')[:96])
    print('      %s' % str(it.get('link') or '')[:100])
    print('      капекс-слово: %s | наша машина: %s | текст %d знаков'
          % ('да' if NS._CAPEX_KW.search(ft or '') else 'нет',
             'да' if MASHINA.search(ft or '') else 'нет', len(ft)))
    print('      %s' % ft[:320])

print('\nИТОГ ' + json.dumps({'сырых': len(items), 'новых': len(novye),
                              'с текстом': s_tekstom, 'капекс': kapeks,
                              'машина названа': mash}, ensure_ascii=False))
