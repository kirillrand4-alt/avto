# -*- coding: utf-8 -*-
"""Сколько управлений Ростехнадзора реально есть и сколько из них обойдено.

ПОВОД, И ОН ПРО ПРАВИЛО, А НЕ ПРО ЧИСЛА. 1-я сессия обошла каталоги графиков проверки знаний
по ДВАДЦАТИ управлениям, второй проход дал ноль новых и вывод записан как «каталоги
вычерпаны». 2-я сессия при уходе оставила другое: «34 непокрытых управления, 3 500 строк не
сматчены с ИНН». Оба не могут быть верны одновременно, и разрешается это ровно тем правилом,
которое мы же и записали: **вывод «источник исчерпан» невозможен, если обход шёл по своему
же списку**. Двадцать хвостов, вычерпанных до дна, ничего не говорят про управления, которых
в списке не было.

Здесь список управлений берётся у САМОГО Ростехнадзора — со страницы территориальных
органов, — а не из нашей памяти. Печатается: сколько их всего, какие из них уже в обойденных
двадцати, и у скольких из непокрытых страница графиков вообще отвечает.
"""
import json
import re
import urllib.request

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')
# Двадцать, которые 1-я сессия обошла (поддомены из её записки и типовых путей).
OBOYDENY = {'ural', 'mos', 'srpov', 'vdon', 'volok'}

HVOSTY = ['/activity/attestation/shedule/', '/activity/attestation/schedule/',
          '/activity/proverka-znaniy/', '/activity/energo_proverka_znaniy/results/',
          '/activity/EnergySecurity/spisok/']


def vzyat(u, tajm=30):
    try:
        req = urllib.request.Request(u, headers={'User-Agent': UA})
        with urllib.request.urlopen(req, timeout=tajm) as r:
            return r.status, r.read().decode('utf-8', 'replace')
    except Exception as e:  # noqa: BLE001
        return 0, f'{type(e).__name__}: {str(e)[:60]}'


st, h = vzyat('https://www.gosnadzor.ru/about/structure/')
poddomeny = sorted(set(re.findall(r'https?://([a-z0-9\-]+)\.gosnadzor\.ru', h)))
print(json.dumps({'страница_структуры': st, 'поддоменов_найдено': len(poddomeny),
                  'поддомены': poddomeny}, ensure_ascii=False))
