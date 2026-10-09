# -*- coding: utf-8 -*-
"""Пилот плана Meyer: разбор слабых мест поиска по журналам (локально, файлы с дропа).

Каждой выдаче (запрос × движок × страница) сопоставляются компании итогового списка: через сайт (домен ->
ИНН/УНП из разбора) или страницу каталога (url -> ИНН). Считается:
  * вклад групп, видов запросов, движков и страниц: сколько компаний списка дали и сколько — ТОЛЬКО они;
  * тест глубины: компании, которые видны только на страницах 2–3;
  * Яндекс против Google на одних и тех же запросах;
  * сайты против каталогов; Беларусь — белорусские формулировки против российских.

    python3 pilot_analiz.py <папка с <набор>-serp.jsonl, -razbor.jsonl, -spisok.json> [out.json] [набор, по умолчанию pilot]
"""
import collections
import json
import os
import re
import sys
import urllib.parse


def хост(u):
    h = (urllib.parse.urlsplit(u if '://' in u else 'http://' + u).hostname or '').lower()
    return h[4:] if h.startswith('www.') else h


def main(п, out=None, набор='pilot'):
    serp = [json.loads(s) for s in open(os.path.join(п, набор + '-serp.jsonl'), encoding='utf-8', errors='replace')]
    serp = [з for з in serp if з.get('итог') == 'ok']
    сайт_кл, кат_кл = collections.defaultdict(set), collections.defaultdict(set)
    for s in open(os.path.join(п, набор + '-razbor.jsonl'), encoding='utf-8', errors='replace'):
        try:
            з = json.loads(s)
        except ValueError:
            continue
        if з.get('тип') == 'сайт':
            кл = {i for i, _ in з.get('инн') or []} | set(з.get('инн_база') or []) | set(з.get('инн_по_имени') or [])
            if not кл:
                кл = {'BY' + у for у, _ in з.get('унп') or []}
            сайт_кл[з['домен']] |= кл
        else:
            кат_кл[з['url']] |= set(з.get('инн_url') or []) | set(з.get('инн') or [])
    сп = json.load(open(os.path.join(п, набор + '-spisok.json'), encoding='utf-8'))
    список = {i for i, к in сп['компании'].items() if not к['откуда'].startswith('реестр')}
    видно = collections.defaultdict(list)  # компания -> [(группа, вид, движок, стр, через, запрос)]
    по_выдаче = []
    for з in serp:
        кк, через = set(), {}
        for д in з['доки']:
            h = хост(д['url'])
            for i in сайт_кл.get(h, ()):
                if i in список:
                    кк.add(i)
                    через.setdefault(i, 'сайт')
            for i in кат_кл.get(д['url'], ()):
                if i in список:
                    кк.add(i)
                    через.setdefault(i, 'каталог')
        for i in кк:
            видно[i].append((з.get('группа', ''), з['вид'], з['движок'], з['стр'], через[i], з['запрос']))
        по_выдаче.append((з, кк))

    def вклад(ключ):
        всего, только = collections.Counter(), collections.Counter()
        запросов = collections.Counter()
        for з, _ in по_выдаче:
            запросов[ключ(з)] += 1
        for i, вв in видно.items():
            кл = {ключ({'группа': в[0], 'вид': в[1], 'движок': в[2], 'стр': в[3]}) for в in вв}
            for к in кл:
                всего[к] += 1
            if len(кл) == 1:
                только[next(iter(кл))] += 1
        return [{'ключ': к, 'запросов': запросов[к], 'компаний списка': всего[к], 'только здесь': только[к],
                 'компаний на 100 запросов': round(100 * всего[к] / max(1, запросов[к]), 1)}
                for к in sorted(запросов, key=lambda x: -всего[x])]

    рез = {'компаний_в_списке_из_поиска': len(список), 'из_них_видны_в_выдаче': len(видно)}
    рез['по_группам'] = вклад(lambda з: з.get('группа', ''))
    рез['по_видам'] = вклад(lambda з: з['вид'])
    рез['по_движкам'] = вклад(lambda з: з['движок'])
    рез['по_страницам'] = вклад(lambda з: 'стр. %d' % з['стр'])
    # тест глубины: только запросы с принудительными 3 страницами (K1, тест_глубины)
    глуб = collections.defaultdict(set)
    for з, кк in по_выдаче:
        if з.get('тест_глубины'):
            глуб[з['стр']] |= кк
    стр1 = глуб.get(1, set())
    рез['глубина'] = {'запросов с 3 страницами': sum(1 for з, _ in по_выдаче if з.get('тест_глубины') and з['стр'] == 1),
                      'компаний на стр. 1': len(стр1),
                      'новых на стр. 2': len(глуб.get(2, set()) - стр1),
                      'новых на стр. 3': len(глуб.get(3, set()) - стр1 - глуб.get(2, set())),
                      'видны ТОЛЬКО на стр. 2–3 во всём пилоте': sum(1 for вв in видно.values() if all(в[3] >= 2 for в in вв))}
    насыщ = [з for з, _ in по_выдаче if not з.get('тест_глубины') and з['стр'] >= 2]
    рез['насыщение'] = {'дозапрошено страниц': len(насыщ),
                        'компаний, найденных только на дозапрошенных страницах': sum(
                            1 for вв in видно.values() if all(в[3] >= 2 for в in вв) and
                            any(в[0] != 'K1' for в in вв))}
    # Яндекс против Google — одни и те же запросы (стр. 1)
    я, г = collections.defaultdict(set), collections.defaultdict(set)
    for з, кк in по_выдаче:
        if з['стр'] == 1:
            (я if з['движок'] == 'yandex' else г)[з['запрос']] |= кк
    общие = set(я) & set(г)
    яя = set().union(*(я[q] for q in общие)) if общие else set()
    гг = set().union(*(г[q] for q in общие)) if общие else set()
    рез['яндекс_против_google'] = {'запросов в обоих': len(общие), 'компаний Яндекс': len(яя), 'компаний Google': len(гг),
                                   'общих': len(яя & гг), 'только Яндекс': len(яя - гг), 'только Google': len(гг - яя)}
    # сайты против каталогов
    через = collections.Counter()
    for i, вв in видно.items():
        вид = {в[4] for в in вв}
        через['и сайт, и каталог' if len(вид) == 2 else 'только ' + next(iter(вид))] += 1
    рез['сайты_против_каталогов'] = dict(через)
    # Беларусь
    by = {i for i in список if i.startswith('BY')}
    рез['беларусь'] = {'компаний (УНП с сайта)': len(by),
                       'нашли белорусские формулировки (B1)': sum(1 for i in by if any(в[0] == 'B1' for в in видно.get(i, []))),
                       'нашли российские шаблоны на Минскую (B1r)': sum(1 for i in by if any(в[0] == 'B1r' for в in видно.get(i, []))),
                       'только B1r': sum(1 for i in by if видно.get(i) and all(в[0] == 'B1r' for в in видно[i]))}
    # запросы, которые ничего не дали
    пустые = collections.Counter(з['вид'] for з, кк in по_выдаче if з['стр'] == 1 and not кк)
    рез['запросы_без_компаний_списка_по_видам'] = dict(пустые)
    txt = json.dumps(рез, ensure_ascii=False, indent=1)
    if out:
        open(out, 'w', encoding='utf-8').write(txt)
    print(txt)
    return рез


if __name__ == '__main__':
    main(*sys.argv[1:4])
