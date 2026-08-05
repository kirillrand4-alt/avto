# -*- coding: utf-8 -*-
"""Сбор по КАЖДОМУ коллектору так, как его зовёт бой: через `collect_all`, а не по одному.

Мой прошлый замер ВК дал ноль, и это дефект ПРИБОРА: я позвала `col_vk(None, None, 14, 10)`
без запросов и без токена. Коллектор не виноват. Значит звать надо тем же способом, каким
зовёт конвейер, — `collect_all(args)`, у которой все умолчания свои.

ЧТО ДЕЛАЕТ. Зовёт `collect_all`, раскладывает сырые items по коллекторам и по каждому
отвечает на три вопроса, которые «ноль» не различает:

    сырых → уникальных → сколько уже в seen_news → НОВЫХ → прошли графу 1

Графа 1 — моя мера повода, починенная (проба 0 провалов из 15): машина → производство →
чужое → косвенный. Она считается ЗДЕСЬ, без провайдера, чтобы отделить «источник пуст»
от «фильтр отсёк».

НЕ ТРОГАЕТ: провайдера (ни одного вызова), seen_news (только чтение). Значит замок не
нужен и квота цела.

Числа печатаются ПОСЛЕДНИМИ: хвост раннера хранит конец вывода, и я уже теряла на этом
и пробу, и список отбракованного.
"""
import collections
import inspect
import json
import os
import re
import sqlite3
import sys
import time

sys.path.insert(0, r'C:\sender\server')
import news_scan as NS  # noqa: E402

BAZA = r'C:\sender\enrich.db'

MASHINA = re.compile(
    r'компрессор\w*|турбокомпрессор\w*|газодувк\w+|газодувн\w+|воздуходувк\w+|'
    r'нагнетател\w+|воздухоразделен\w+|воздухоразделительн\w+|\bВРУ\b|\bКСУ\b|'
    r'сжат\w+\s+воздух\w*|сжатого\s+газа|пневмат\w+|пневмосистем\w+|'
    r'осушител\w+\s+возду\w+|осушк\w+\s+возду\w+|'
    r'генератор\w*\s+(?:азота|кислорода)|азотн\w+\s+станци\w+|кислородн\w+\s+станци\w+|'
    r'\bазот\w*\b|\bкислород\w*\b|холодильн\w+\s+машин\w+|\bчиллер\w*|\bресивер\w*|'
    r'центробежн\w+\s+(?:компрессор\w*|машин\w+|нагнетател\w+)', re.I)
PROIZVODSTVO = re.compile(
    r'\b\w*завод\w*|\bцех\w*|\bпроизводств\w*|\b\w*комбинат\w*|\bфабрик\w*|\bэлеватор\w*|'
    r'\bпроизводственн\w+|\bтехнологическ\w+\s+лини\w+|\bмощност\w+\s+\d|\bагрегат\w*|'
    r'\bустановк\w+|\bпереработк\w+|\bобогатительн\w+|\bметаллург\w+|'
    r'\bНПЗ\b|\bГОК\b|\bТЭЦ\b|\bГРЭС\b|\bкотельн\w+|\bдобыч\w+|\bрудник\w*|\bшахт\w+', re.I)
CHUZHOE = re.compile(
    r'\bлогистическ\w+\s+(?:комплекс\w*|центр\w*)|\bсклад\w+\s+комплекс\w*|'
    r'\bторгов\w+\s+центр\w*|\bбизнес-центр\w*|\bжил\w+\s+(?:комплекс\w*|дом\w*|квартал\w*)|'
    r'\bдетск\w+\s+сад\w*|\bшкол\w+|\bбольниц\w+|\bполиклиник\w+|\bстадион\w*|'
    r'\bфельдшерск\w+|\bФАП\b|\bамбулатор\w+|\bавтосалон\w*|\bдилерск\w+\s+центр\w*|'
    r'\bофисн\w+\s+(?:здани\w+|помещени\w+|центр\w*)|\bблагоустройств\w+|'
    r'\bавтомобильн\w+\s+дорог\w+|\bмост\b|\bмоста\b|\bпутепровод\w*|\bтротуар\w*|'
    r'\bнабережн\w+', re.I)


def grafa1(t):
    t = t or ''
    if MASHINA.search(t):
        return 'ПРЯМОЙ'
    if PROIZVODSTVO.search(t):
        return 'КОСВЕННЫЙ'
    if CHUZHOE.search(t):
        return 'ЧУЖОЙ'
    return 'КОСВЕННЫЙ'


print('news_scan.__file__ = %s' % NS.__file__)
print('\n=== collect_all: какие умолчания у неё внутри')
try:
    for l in inspect.getsource(NS.collect_all).split('\n')[:70]:
        print('   %s' % l[:160])
except Exception as e:  # noqa: BLE001
    print('   %s' % e)

# ключи дедупа — только читаем
kluchi = set()
if os.path.exists(BAZA):
    cx = sqlite3.connect('file:%s?mode=ro' % BAZA.replace('\\', '/'), uri=True)
    try:
        kluchi = set(r[0] for r in cx.execute('select k from seen_news'))
    except Exception:  # noqa: BLE001
        pass
    cx.close()
print('\nключей в seen_news: %d' % len(kluchi))

t0 = time.time()
try:
    raw = NS.collect_all({}) or []
except Exception as e:  # noqa: BLE001
    print('collect_all({}) упал: %s: %s' % (type(e).__name__, str(e)[:200]))
    raw = []
print('collect_all вернула %d items за %.0f с' % (len(raw), time.time() - t0))

po = collections.defaultdict(lambda: {'сырых': 0, 'уникальных': 0, 'уже видены': 0,
                                      'новых': 0, 'ПРЯМОЙ': 0, 'КОСВЕННЫЙ': 0,
                                      'ЧУЖОЙ': 0})
vidal = collections.defaultdict(set)
glazami = []
for it in raw:
    k_ = it.get('collector') or it.get('source') or '?'
    z = po[k_]
    z['сырых'] += 1
    try:
        key = NS._news_key(it)
    except Exception:  # noqa: BLE001
        key = None
    if not key or key in vidal[k_]:
        continue
    vidal[k_].add(key)
    z['уникальных'] += 1
    if key in kluchi:
        z['уже видены'] += 1
        continue
    z['новых'] += 1
    tekst = (str(it.get('title') or '') + ' ' + str(it.get('full_text') or ''))[:6000]
    u = grafa1(tekst)
    z[u] += 1
    if len(glazami) < 10 and u in ('ПРЯМОЙ', 'КОСВЕННЫЙ'):
        glazami.append((k_, u, it))

print('\n\n########## ДЕСЯТЬ НОВОСТЕЙ ГЛАЗАМИ (повод настоящий? про эту компанию?)')
for k_, u, it in glazami:
    ft = re.sub(r'\s+', ' ', str(it.get('full_text') or it.get('title') or ''))
    print('\n  [%s] %s' % (k_, u))
    print('    заголовок: %s' % str(it.get('title') or '')[:150])
    print('    ссылка:    %s' % str(it.get('link') or '')[:110])
    print('    текст (%d знаков): %s' % (len(ft), ft[:600]))

print('\n\n########## ЧИСЛА ПО КОЛЛЕКТОРАМ (цель: по 10 свежих уникальных)')
print('  %-18s %6s %6s %6s %6s | %6s %6s %6s'
      % ('коллектор', 'сырых', 'уник', 'видены', 'НОВЫХ', 'прямых', 'косв', 'чужих'))
itog = {}
for k_ in sorted(po, key=lambda x: -po[x]['новых']):
    z = po[k_]
    print('  %-18s %6d %6d %6d %6d | %6d %6d %6d'
          % (k_[:18], z['сырых'], z['уникальных'], z['уже видены'], z['новых'],
             z['ПРЯМОЙ'], z['КОСВЕННЫЙ'], z['ЧУЖОЙ']))
    itog[k_] = z
for k_ in ('vk', 'google', 'zakupki', 'hh', 'frp', 'regional',
           'xmlriver-google', 'xmlriver-yandex'):
    if k_ not in po:
        print('  %-18s НЕ ВЕРНУЛ НИ ОДНОГО ITEM (коллектор не стартовал или пуст)' % k_)
        itog[k_] = {'сырых': 0, 'новых': 0, 'причина': 'items нет вовсе'}

print('\nИТОГ ' + json.dumps(itog, ensure_ascii=False))
