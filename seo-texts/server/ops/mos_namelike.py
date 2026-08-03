# -*- coding: utf-8 -*-
"""Подобрать форму nameLike для old.zakupki.mos.ru по снятому queryDto.

Захват живого фронта показал: nameLike это ОБЪЕКТ {"contains":true}, а не
строка — все 500-е у 3-й сессии были от неверного типа поля. Здесь пробуем
кандидатов на имя поля со значением внутри объекта. Эталон — счётчик пустого
запроса: чужое поле молча игнорируется и счётчик не меняется (метод 3-й
сессии), своё поле с текстом обязано счётчик обрушить.
"""
import json
import urllib.parse
import urllib.request

БАЗА = 'https://old.zakupki.mos.ru/api/Cssp/Purchase/Query'
ШАБЛОН = {"filter": {"typeIn": {}, "nameLike": {"contains": True},
                     "regionPaths": {}, "customerInnOrName": {"contains": True},
                     "numberLike": {"contains": True},
                     "externalNumberLike": {"contains": True},
                     "auctionSpecificFilter": {"stateIdIn": [19000002, 19000005,
                                                             19000003, 19000004,
                                                             19000008],
                                               "initialDuration": [3, 6, 24],
                                               "supplierTotalPoints": {}},
                     "needSpecificFilter": {"supplierTotalPoints": {}},
                     "tenderSpecificFilter": {}, "ptkrSpecificFilter": {}},
          "order": [{"field": "relevance", "desc": True}],
          "withCount": True, "take": 1, "skip": 0}


def спрос(дто):
    у = БАЗА + '?queryDto=' + urllib.parse.quote(json.dumps(дто, ensure_ascii=False))
    з = urllib.request.Request(у, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(з, timeout=60) as о:
            д = json.loads(о.read().decode('utf-8', 'replace'))
        return д.get('count'), (д.get('items') or [{}])[0].get('name', '')[:60]
    except Exception as e:  # noqa: BLE001
        return f'ОШИБКА {str(e)[:60]}', ''


def main():
    import copy
    эталон, _ = спрос(ШАБЛОН)
    print(f'эталон (без текста): {эталон}')
    for поле in ('value', 'like', 'text', 'name', 'pattern', 'query', 'str'):
        дто = copy.deepcopy(ШАБЛОН)
        дто['filter']['nameLike'][поле] = 'компрессор'
        счёт, имя = спрос(дто)
        метка = ' <-- РАБОТАЕТ' if isinstance(счёт, int) and счёт != эталон else ''
        print(f'nameLike.{поле:8} -> {счёт}{метка}  {имя}')


if __name__ == '__main__':
    main()
