# -*- coding: utf-8 -*-
r"""Третий файл базы Meyer (владелец 06.10): номера БЕЗ ролей, «но номер точно должен
быть на странице». Модель не нужна — проверяется только наличие номера на живой
странице-источнике (в любом написании, в т.ч. в tel:-ссылке и слитно с 8).

Вход: C:\seostat\drop\drop-storage\meyer-nalichie-vhod.json — страницы
{url, inn, номера:[{id, номер, ...}]}. Выход (fsync, резюм по id):
C:\sender\server\meyer-nalichie.jsonl — на номер: страница (ok/ошибка), найден (раз),
контекст вокруг номера; если на живой странице нет — есть ли в кэше обхода (для
справки: такой номер «точно на странице» НЕ считается).
Запуск: python meyer_nalichie.py [--povtor]; детачем — _pusk_nalichiya.py.
"""
import io
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
import meyer_proverka as MP  # noqa: E402  (в_текст, найти, из_кэша_обхода)

ВХОД = r'C:\seostat\drop\drop-storage\meyer-nalichie-vhod.json'
ВЫХОД = os.path.join(DIR, 'meyer-nalichie.jsonl')
ПОТОКОВ = 32
_лок = threading.Lock()
# Чья страница: во втором файле модель нашла 39 из 195 номеров на страницах ЧУЖИХ компаний
# (справочники вроде foodsuppliers.ru). Номер «на странице» без этой проверки — не довод.
КОМП = {}  # инн -> (ядро названия, {домены сайта})
ОПФ = re.compile(r'^(ООО|АО|ПАО|ЗАО|ОАО|НАО|ИП|СПК|КФХ|ГУП|МУП|ФГУП|ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ|'
                 r'АКЦИОНЕРНОЕ ОБЩЕСТВО|ПУБЛИЧНОЕ АКЦИОНЕРНОЕ ОБЩЕСТВО)\b', re.I)


def домен(u):
    u = (u or '').strip().lower()
    u = re.sub(r'^[a-z]+://', '', u).split('/')[0].split(':')[0]
    u = u[4:] if u.startswith('www.') else u
    ч = u.split('.')
    return '.'.join(ч[-2:]) if len(ч) >= 2 else u


def загрузить_компании(инн):
    import sqlite3
    c = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True, timeout=120)
    c.execute(r"attach database 'file:C:\sender\obzvon-index.db?mode=ro' as obz")
    c.execute('create temp table t(inn text primary key)')
    c.executemany('insert or ignore into t values (?)', [(i,) for i in инн])
    for i, имя, кор, сайт, сайт2, имя2 in c.execute(
            "select t.inn, coalesce(c.name,''), coalesce(c.short_name,''), coalesce(c.site,''), "
            "coalesce(o.sites,''), coalesce(o.name_short,'') from t left join companies c on c.inn=t.inn "
            'left join obz.obzvon o on o.inn=t.inn'):
        ядра = set()
        for н in (имя, кор, имя2):
            for кус in re.findall(r'[«"]+([^«»"]{3,})[»"]+', н or ''):
                ядра.add(re.sub(r'\s+', ' ', кус).strip().lower())
            голое = ОПФ.sub('', (н or '').replace('"', ' ').replace('«', ' ').replace('»', ' ')).strip()
            if len(голое) >= 4:
                ядра.add(re.sub(r'\s+', ' ', голое).lower())
        домены = {домен(x) for x in re.split(r'[\s,;|]+', сайт + ' ' + сайт2) if '.' in x}
        КОМП[i] = (ядра, домены)
    c.close()


def чья(inn, url, текст):
    ядра, домены = КОМП.get(inn, (set(), set()))
    if домен(url) in домены:
        return 'да: свой сайт'
    if inn in текст:
        return 'да: ИНН на странице'
    низ = re.sub(r'\s+', ' ', текст.lower().replace('«', '"').replace('»', '"'))
    for я in ядра:
        if len(я) >= 4 and я in низ:
            return 'да: название на странице'
    return 'нет: ни сайта, ни ИНН, ни названия'


import ssl  # noqa: E402
import urllib.error  # noqa: E402
import urllib.parse  # noqa: E402
import urllib.request  # noqa: E402
_прямой = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_без_серт = urllib.request.build_opener(
    urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=ssl._create_unverified_context()))
_хосты, _хосты_лок = {}, threading.Lock()


def скачать(url):
    """Быстрый скачок для проверки наличия: одна попытка напрямую (15 с); сертификат —
    только при ошибке сертификата; прокси — только при обрыве/403; 429/503 — одна пауза."""
    хост = urllib.parse.urlsplit(url).hostname or ''
    with _хосты_лок:
        лок = _хосты.setdefault(хост, threading.Lock())
    req = urllib.request.Request(MP.ascii_url(url), headers={
        'User-Agent': MP.UA, 'Accept-Language': 'ru-RU,ru;q=0.9',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'})

    def открыть(opener):
        r = urllib.request.urlopen(req, timeout=15) if opener is None else opener.open(req, timeout=15)
        with r:
            return r.headers.get('Content-Type', ''), r.read(6_000_000)
    ошибка = ''
    with лок:
        план = [_прямой]
        while план:
            opener = план.pop(0)
            try:
                тип, сырое = открыть(opener)
                if 'pdf' in тип.lower():
                    return 'pdf', '', ''
                м = re.search(r'charset=([\w\-]+)', тип) or re.search(rb'charset=["\']?([\w\-]+)', сырое[:3000])
                кодир = (м.group(1) if isinstance(м.group(1), str) else м.group(1).decode('ascii', 'ignore')) if м else 'utf-8'
                try:
                    текст = сырое.decode(кодир, errors='replace')
                except LookupError:
                    текст = сырое.decode('utf-8', errors='replace')
                з = re.search(r'<title[^>]*>(.*?)</title>', текст, re.S | re.I)
                return 'ok', текст, (MP.html.unescape(з.group(1)).strip()[:150] if з else '')
            except urllib.error.HTTPError as e:
                ошибка = 'HTTP %s' % e.code
                if e.code in (429, 503) and opener is _прямой and not план:
                    time.sleep(10)
                    план = [_без_серт]
                elif e.code == 403 and opener is not None:
                    план = [None]
            except Exception as e:  # noqa: BLE001
                ошибка = type(e).__name__ + ': ' + str(e)[:60]
                т = str(e).lower()
                if 'certificate' in т or 'ssl' in т:
                    if opener is _прямой:
                        план = [_без_серт]
                elif 'getaddrinfo' in т or 'name or service' in т:
                    break
                elif opener is not None and opener is not _без_серт and not план:
                    план = [None]
    return 'ошибка: ' + ошибка, '', ''


def записать(записи):
    with _лок:
        with io.open(ВЫХОД, 'a', encoding='utf-8') as f:
            for з in записи:
                f.write(json.dumps(з, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())


def страница(стр):
    статус, сырое, заголовок = скачать(стр['url'])
    текст = MP.в_текст(сырое) if статус == 'ok' else ''
    своя = чья(стр['inn'], стр['url'], текст) if текст else ''
    записи = []
    for н in стр['номера']:
        цифры = re.sub(r'\D', '', н['номер'])[-10:]
        поз = MP.найти(текст, цифры) if текст else []
        з = {'id': н['id'], 'inn': стр['inn'], 'url': стр['url'], 'страница': статус,
             'заголовок': заголовок, 'найден': len(поз), 'компания_на_странице': своя}
        if поз:
            з['контекст'] = re.sub(r'\s+', ' ', текст[max(0, поз[0] - 160):поз[0] + 60])
        else:
            к = MP.из_кэша_обхода(стр['inn'], цифры)
            if к:
                з['в_кэше_обхода'] = '%s: %s' % (к[2][:10], к[0][:100])
        записи.append(з)
    записать(записи)


def main():
    повтор = '--povtor' in sys.argv
    вход = json.load(io.open(ВХОД, encoding='utf-8'))
    загрузить_компании(sorted({стр['inn'] for стр in вход}))
    print('компаний с названием/сайтом', len(КОМП), flush=True)
    сделано = {}
    if os.path.exists(ВЫХОД):
        for s in io.open(ВЫХОД, encoding='utf-8', errors='replace'):
            try:
                з = json.loads(s)
                сделано[з['id'] + '|' + з['url']] = з.get('страница')
            except ValueError:
                pass
    очередь = []
    for стр in вход:
        ост = [н for н in стр['номера'] if (н['id'] + '|' + стр['url']) not in сделано
               or (повтор and сделано[н['id'] + '|' + стр['url']] != 'ok')]
        if ост:
            очередь.append(dict(стр, номера=ост))
    print('страниц', len(вход), 'в очереди', len(очередь), flush=True)
    t0 = time.time()
    счёт = [0]

    def один(стр):
        try:
            страница(стр)
        except Exception as e:  # noqa: BLE001
            print('сбой', стр['url'][:80], repr(e)[:100], flush=True)
        счёт[0] += 1
        if счёт[0] % 500 == 0:
            print('готово страниц %d за %d мин' % (счёт[0], (time.time() - t0) / 60), flush=True)

    with ThreadPoolExecutor(ПОТОКОВ) as ex:
        list(ex.map(один, очередь))
    print('готово', flush=True)


if __name__ == '__main__':
    main()
