#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Куда на самом деле ложится каждая статья.

    python3 kuda_lozhitsya.py

ВОПРОС ВЛАДЕЛЬЦА: «лягут ли статьи на нужные категории». Ответ оказался
неприятным: адрес в шапке ТЗ - ПЛАНОВЫЙ. Из 133 целей живы 28, остальные
105 отдают 404. У kraftmann слуги совпали с настоящими случайно (11 из 11),
у remeza не совпал ни один.

Здесь ищем настоящего адресата: по теме статьи подбираем существующий
раздел каталога того же сайта. Три исхода:
  ЕСТЬ      целевой адрес из ТЗ живой, класть можно как есть;
  ДРУГОЙ    раздел есть, но зовётся иначе - класть надо туда;
  НЕТ       подходящего раздела на сайте нет, страницу придётся создавать.

Совпадение считаем по СЛОВАМ ТЕМЫ, а не по строковой близости: «осушители»
и «ochistka-szhatogo-vozdukha» не похожи побуквенно, но это одно и то же.
"""
import json
import os
import re

DIR = os.path.dirname(os.path.abspath(__file__))

# Тема статьи -> слова, по которым узнаётся раздел на сайте.
# Слова ищутся и в адресе раздела, и в его подписи.
TEMY = {
    'vintovye-kompressory':      ['vintov', 'винтов'],
    'porshnevye-kompressory':    ['porshn', 'поршнев'],
    'spiralnye-kompressory':     ['spiraln', 'спиральн'],
    'dizelnye-kompressory':      ['dizeln', 'дизельн'],
    'tsentrobezhnye-kompressory': ['tsentrobezh', 'centrobezh', 'центробеж'],
    'dozhimnye-kompressory':     ['dozhim', 'booster', 'дожим', 'бустер'],
    'bezmaslyanye-kompressory':  ['bezmasl', 'безмасл'],
    'osushiteli':                ['osushit', 'осушит', 'ochistka-szhatogo', 'подготовк'],
    'filtry-magistralnye':       ['filtr', 'фильтр'],
    'tsiklonnye-separatory':     ['separator', 'ciklon', 'tsiklon', 'сепаратор', 'циклон',
                                  'vlagootdel', 'влагоотдел'],
    'resivery':                  ['resiver', 'ресивер'],
    'azotnaya-stanciya':         ['azot', 'азот'],
    'azotnaya-stanciya-modulnaya': ['azot', 'азот'],
    'generatory-azota':          ['azot', 'азот'],
    'kislorodnaya-stanciya':     ['kislorod', 'кислород'],
    'kislorodnaya-stanciya-modulnaya': ['kislorod', 'кислород'],
    'generatory-kisloroda':      ['kislorod', 'кислород'],
    'kompressornaya-stanciya':   ['stanci', 'stanci', 'станци', 'kompressornaya'],
    'mks':                       ['modul', 'модул', 'blochn', 'блочн', 'konteyner', 'контейнер'],
}


def tema(slug):
    return slug.split('--', 1)[1] if '--' in slug else slug


def podhodit(slova, put, imya):
    stroka = (put + ' ' + imya).lower()
    return any(s in stroka for s in slova)


def main():
    kat = json.load(open(os.path.join(DIR, 'kategorii-saytov.json'), encoding='utf-8'))
    celi = {z['slug']: z for z in json.load(open(os.path.join(DIR, 'celi-proverka.json'), encoding='utf-8'))}
    from k_publikacii import DOMEN

    itog = []
    for slug in sorted(celi):
        dom = DOMEN[slug.split('--')[0]]
        c = celi[slug]
        t = tema(slug)
        slova = TEMY.get(t)
        if c['kod'] == '200':
            itog.append({'slug': slug, 'ishod': 'ЕСТЬ', 'kuda': c['url'], 'kandidaty': []})
            continue
        kandidaty = []
        if slova:
            d = kat.get(dom, {})
            for put in d.get('puti', []):
                imya = d.get('imena', {}).get(put, '')
                if podhodit(slova, put, imya):
                    kandidaty.append((put, imya))
        # МОДУЛЬНАЯ ОТ ОБЫЧНОЙ ОТЛИЧАЕТСЯ: если тема про модуль, а раздел
        # про модуль не говорит - это не он, а просто азотный раздел.
        itog.append({'slug': slug,
                     'ishod': 'ДРУГОЙ' if kandidaty else 'НЕТ',
                     'kuda': f"https://{dom}{kandidaty[0][0]}" if kandidaty else '',
                     'kandidaty': [f"{p} ({i})" if i else p for p, i in kandidaty[:4]]})

    json.dump(itog, open(os.path.join(DIR, 'kuda-lozhitsya.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    import collections
    sch = collections.Counter(z['ishod'] for z in itog)
    print('ИТОГ:', dict(sch))
    print('\nНЕТ ПОДХОДЯЩЕГО РАЗДЕЛА:')
    for z in itog:
        if z['ishod'] == 'НЕТ':
            print(f"   {z['slug']}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
