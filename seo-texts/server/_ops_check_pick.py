# -*- coding: utf-8 -*-
"""Разведка №1 (без сети): кого вообще проверять и что видит наш код ДО обхода.

Задача — не поверить чужому выводу «hh пуст», а сначала убедиться, что мы
меряем правильные компании и что бренд для поиска строится осмысленно.
"""
import json
import os
import re
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402

БАЗА = r'C:\sender\_ops\sales_base.json'


def main():
    d = json.load(open(БАЗА, encoding='utf-8'))
    строки = []
    if isinstance(d, dict):
        for v in d.values():
            if isinstance(v, list):
                строки += v
    elif isinstance(d, list):
        строки = d
    print('ВСЕГО строк в базе:', len(строки))
    if строки:
        print('КЛЮЧИ строки:', sorted(строки[0].keys())[:25])
    # ищем заведомо крупные/известные — у них вакансии на hh точно есть
    маркеры = ('ростелеком', 'северсталь', 'нлмк', 'сибур', 'газпром', 'лукойл',
               'росатом', 'уралхим', 'фосагро', 'магнитогорск', 'евраз',
               'криогенмаш', 'уралэлектромедь', 'акрон', 'татнефть', 'русал',
               'челябинск', 'камаз', 'автоваз', 'пивовар', 'молоч', 'хлебо',
               'металлург', 'завод')
    найдено = []
    for x in строки:
        n = str(x.get('name') or '')
        nl = n.lower()
        for m in маркеры:
            if m in nl:
                найдено.append((m, str(x.get('inn') or ''), n[:70],
                                str(x.get('site') or '')))
                break
    print('строк с маркерами:', len(найдено))
    видели = set()
    показ = []
    for m, inn, n, s in найдено:
        if m in видели or not inn:
            continue
        видели.add(m)
        показ.append({'инн': inn, 'имя': n, 'сайт': s,
                      'бренд': EC.бренд_компании(n, s)})
        if len(показ) >= 14:
            break
    for p in показ:
        print(json.dumps(p, ensure_ascii=False))
    print('XMLRIVER_USER:', bool(os.environ.get('XMLRIVER_USER')),
          'XMLRIVER_KEY:', bool(os.environ.get('XMLRIVER_KEY')),
          'DOLPHIN:', bool(EC._read_secret('DOLPHIN_TOKEN')),
          'NO_BROWSER:', EC._NO_BROWSER)
    print('ИТОГ: строк=%d кандидатов=%d' % (len(строки), len(показ)))


if __name__ == '__main__':
    main()
