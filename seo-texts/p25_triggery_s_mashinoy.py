# -*- coding: utf-8 -*-
"""Триггеры, которые НАЗЫВАЮТ нашу машину — против готовых. Замер до/после на одном канале.

ЧТО ПОКАЗАЛО ЧТЕНИЕ ГОТОВЫХ СЛОВАРЕЙ. `TRIGGERS` (11 штук) — чистый капекс-язык:
«строительство завода», «новый цех», «модернизация производства». Наша машина не названа
ни в одном. Запросы строятся TRIGGERS × отрасли, и урожай выходит такой:

    Проект завода гигантских шин в Омске
    Мясоперерабатывающий завод вводят в Астане          <- Казахстан
    Власти Таджикистана готовят запуск цементных заводов
    из 22 новых google-новостей ПРЯМЫХ (машина названа) — НОЛЬ

А `HH_SIGNALS` в том же файле сделан наоборот: «машинист компрессорных установок»,
«оператор компрессорной станции», «слесарь по ремонту компрессорного оборудования». И
результат: 445 сигналов из hh-вакансий, ВСЕ 445 прямые. Образец уже есть в репозитории,
просто он применён к вакансиям и не применён к новостям.

ЧТО ДЕЛАЕТ ЭТОТ ЗАМЕР. Гоняет ОДИН И ТОТ ЖЕ коллектор (`col_google`) двумя наборами
запросов — готовым и моим — и считает по каждому: сырых, уникальных, новых (не в
seen_news), и сколько из них ПРЯМЫХ. Сравнение честное: канал один, дни одни, потолок
один. Провайдера не трогает.

ЗАСЛОН ОТ САМООБМАНА. Мой набор называет машину прямо, поэтому «нашлось про компрессоры»
гарантировано и ничего не доказывает. Доказывает другое: сколько НОВЫХ РОССИЙСКИХ
предприятий с капексом он приносит. Поэтому считаю отдельно: не-РФ по домену и словам,
и повторы с готовым набором.
"""
import collections
import json
import os
import re
import sqlite3
import sys

sys.path.insert(0, r'C:\sender\server')
import news_scan as NS  # noqa: E402

BAZA = r'C:\sender\enrich.db'
DAYS = 14
MAX = 10

# Мой набор. Форма скопирована с HH_SIGNALS: машина названа прямо, без «модернизации вообще».
MOI = [
    'новая компрессорная станция',
    'модернизация компрессорной станции',
    'замена компрессора на заводе',
    'закупка компрессорного оборудования',
    'воздухоразделительная установка',
    'азотная станция предприятие',
    'кислородная станция завод',
    'генератор азота производство',
    'система сжатого воздуха цех',
    'турбокомпрессор завод',
    'газодувная машина',
    'осушитель сжатого воздуха',
    'центробежный компрессор модернизация',
    'компрессорная установка ввод в эксплуатацию',
    'пневмосистема производства',
]

MASHINA = re.compile(
    r'компрессор\w*|турбокомпрессор\w*|газодувк\w+|газодувн\w+|воздуходувк\w+|'
    r'нагнетател\w+|воздухоразделен\w+|воздухоразделительн\w+|\bВРУ\b|\bКСУ\b|'
    r'сжат\w+\s+воздух\w*|пневмат\w+|пневмосистем\w+|осушк\w+\s+возду\w+|'
    r'осушител\w+\s+возду\w+|генератор\w*\s+(?:азота|кислорода)|'
    r'азотн\w+\s+станци\w+|кислородн\w+\s+станци\w+|\bчиллер\w*', re.I)
NE_RF = re.compile(
    r'казахстан|астан[ае]|алмат|атырау|шымкент|караганд|таджикистан|душанбе|'
    r'узбекистан|ташкент|киргиз|бишкек|беларус|минск|украин|киев|умань|харьков|'
    r'армени|ереван|азербайджан|баку|туркмен|молдов|\.kz\b|\.uz\b|\.ua\b|\.by\b|'
    r'\.tj\b|\.kg\b|\.am\b|\.az\b', re.I)


def kak_v_boyu():
    inds = list(NS.KC_INDUSTRIES) + list(NS.MEYER_INDUSTRIES)
    return ['%s %s' % (t, ind) for t in NS.TRIGGERS[:6] for ind in inds]


kluchi = set()
if os.path.exists(BAZA):
    cx = sqlite3.connect('file:%s?mode=ro' % BAZA.replace('\\', '/'), uri=True)
    try:
        kluchi = set(r[0] for r in cx.execute('select k from seen_news'))
    except Exception:  # noqa: BLE001
        pass
    cx.close()
print('news_scan.__file__ = %s' % NS.__file__)
print('ключей в seen_news: %d' % len(kluchi))
print('готовых запросов: %d, моих: %d' % (len(kak_v_boyu()), len(MOI)))

NABORY = [('ГОТОВЫЙ (TRIGGERS x отрасли)', kak_v_boyu()),
          ('МОЙ (машина названа)', MOI)]

itog = {}
pokaz = {}
kluchi_nabora = {}
for imya, zaprosy in NABORY:
    try:
        items = NS.col_google(zaprosy, DAYS, MAX) or []
    except Exception as e:  # noqa: BLE001
        print('\n%s: коллектор упал: %s' % (imya, str(e)[:140]))
        itog[imya] = {'упал': type(e).__name__}
        continue
    vidal, novye = set(), []
    for it in items:
        try:
            k = NS._news_key(it)
        except Exception:  # noqa: BLE001
            k = None
        if not k or k in vidal:
            continue
        vidal.add(k)
        if k not in kluchi:
            novye.append((k, it))
    kluchi_nabora[imya] = set(k for k, _ in novye)
    pryamyh, chuzhaya_strana, kapeks = [], 0, 0
    for k, it in novye:
        t = str(it.get('title') or '')
        if MASHINA.search(t):
            pryamyh.append(it)
        if NE_RF.search(t + ' ' + str(it.get('link') or '')):
            chuzhaya_strana += 1
        if NS._CAPEX_KW.search(t):
            kapeks += 1
    itog[imya] = {'сырых': len(items), 'уникальных': len(vidal), 'новых': len(novye),
                  'ПРЯМЫХ (машина названа)': len(pryamyh),
                  'прошли бы капекс-предфильтр': kapeks,
                  'НЕ РФ (платим за них зря)': chuzhaya_strana}
    pokaz[imya] = ([it for _, it in novye][:6], pryamyh[:6])

# пересечение наборов: приносит ли мой набор ДРУГИЕ новости, а не те же самые
if len(kluchi_nabora) == 2:
    a, b = list(kluchi_nabora.values())
    print('\nобщих ключей у двух наборов: %d (мой приносит СВОИХ %d)'
          % (len(a & b), len(b - a)))

print('\n\n########## ЧТО ПРИНЕС КАЖДЫЙ НАБОР — ГЛАЗАМИ')
for imya, (novye, pryamyh) in pokaz.items():
    print('\n===== %s' % imya)
    print('  --- новые вообще:')
    for it in novye:
        print('    · %s' % str(it.get('title') or '')[:120])
    print('  --- из них ПРЯМЫЕ (наша машина названа):')
    for it in pryamyh:
        print('    · %s' % str(it.get('title') or '')[:120])
        print('      %s' % str(it.get('link') or '')[:110])
    if not pryamyh:
        print('    (ни одной)')

print('\n\n########## ЧИСЛА')
for imya, z in itog.items():
    print('  %-32s %s' % (imya[:32], json.dumps(z, ensure_ascii=False)))
print('ИТОГ ' + json.dumps(itog, ensure_ascii=False))
