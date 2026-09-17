# -*- coding: utf-8 -*-
"""Опознание двух карточек через поиск: молочноконсервный комбинат в СФО и завод роботов."""
import json
import os
import re
import urllib.parse
import urllib.request

U = os.environ.get('XMLRIVER_USER', '')
K = os.environ.get('XMLRIVER_KEY', '')
НП = urllib.request.build_opener(urllib.request.ProxyHandler({}))
o = {'баланс_до': None, 'баланс_после': None}


def баланс():
    try:
        with НП.open('http://xmlriver.com/api/get_balance/?user=%s&key=%s' % (U, K),
                     timeout=30) as r:
            return r.read(60).decode('utf-8', 'replace').strip()
    except Exception as e:
        return repr(e)[:50]


def искать(запрос, движок='yandex', групп=6):
    база = ('http://xmlriver.com/search/xml' if движок == 'yandex'
            else 'http://xmlriver.com/search_google/xml')
    url = '%s?user=%s&key=%s&query=%s&groupby=%d' % (
        база, U, K, urllib.parse.quote(запрос), групп)
    try:
        with НП.open(url, timeout=90) as r:
            xml = r.read(400000).decode('utf-8', 'replace')
    except Exception as e:
        return ['ОШИБКА: %r' % (e,)]
    вывод = []
    for блок in re.findall(r'<doc>(.*?)</doc>', xml, re.S)[:групп]:
        т = (re.search(r'<title>(.*?)</title>', блок, re.S) or ['', ''])[1]
        п = (re.search(r'<passage>(.*?)</passage>', блок, re.S) or
             re.search(r'<contentType[^>]*>(.*?)</', блок, re.S) or ['', ''])[1]
        u = (re.search(r'<url>(.*?)</url>', блок, re.S) or ['', ''])[1]
        чист = lambda s: re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', s)).strip()  # noqa: E731
        вывод.append({'заголовок': чист(т)[:110], 'текст': чист(п)[:220],
                      'ссылка': чист(u)[:80]})
    return вывод


o['баланс_до'] = баланс()
o['молочноконсервный_СФО'] = искать(
    'реконструкция расширение молочноконсервного комбината 2026 Сибирь')
o['молочноконсервный_2'] = искать(
    '"молочноконсервный комбинат" модернизация 2026 Омская Кемеровская Алтайский',
    движок='google')
o['завод_роботов'] = искать(
    'создание производства промышленных роботов завод 2025 инвестпроект')
o['завод_роботов_2'] = искать(
    'строительство завода промышленных роботов Россия 2025 млн инвестиции',
    движок='google')
o['баланс_после'] = баланс()
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1)[:5600])
