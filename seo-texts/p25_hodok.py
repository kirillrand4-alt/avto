# -*- coding: utf-8 -*-
"""Один ходок за страницей сайта на все модули P25. Два захода, и путь пишется в провенанс.

ПОЧЕМУ НЕ «ВКЛЮЧИТЬ ФЛАГ ВСЕГДА». Поправка 1-й сессии, и она права по существу:
`ignore_https_errors` выключает проверку подлинности сервера. Для публичной страницы ради
имени и должности это приемлемо — строка всё равно принимается только с цитатой и ссылкой, —
но включённый на всех подряд он теряет признак подмены там, где тот работает. Поэтому:

    первый заход  — честно, без флага;
    второй заход  — только если первый не дошёл до сайта;
    поле `kak`    — каким путём страница взята, и оно ОБЯЗАНО доезжать до журнала.

КАК ОТЛИЧАЕМ СЕРТИФИКАТ ОТ МЁРТВОГО ДОМЕНА — ПОВЕДЕНИЕМ, А НЕ ТЕКСТОМ ОШИБКИ. Разбирать
строку `ERR_CERT_AUTHORITY_INVALID` заманчиво, но она приходит не всегда и на разных языках.
Надёжнее спросить саму страницу: если браузер остался на заглушке, `location.origin` равен
строке `"null"` — сайт не открылся, что бы там ни было написано. Тогда второй заход с флагом
и разводит два класса:

    первый заход null, второй открылся  → сертификат (`kak` = «без проверки сертификата»)
    оба захода null                     → домен не обслуживается, флаг ни при чём

Замер, на котором это построено:
    alrosa.ru        null → открылся, «АЛРОСА | Корпоративный сайт»
    uacrussia.ru     null → открылся, «Объединенная авиастроительная корпорация»
    kurganpribor.ru  null → null, домен отдаёт 503 «сайт не добавлен на хостинг»

Свалить все три в один класс «российский сертификат» значило бы на третьем предприятии
искать не там, где надо.
"""
import json
import os
import subprocess
import sys

BAZA = os.path.dirname(os.path.abspath(__file__))
KLIENT = os.path.join(BAZA, 'server', 'run_on_server.py')

# ПАМЯТЬ ПО ХОСТАМ. Правило «флаг только вторым заходом» верное, но буквальное его исполнение
# удваивает запросы там, где ответ уже известен: у ЕИС (`zakupki.gov.ru`) сертификат НУЦ
# Минцифры, и первый заход обречён на каждой из 70 тысяч карточек. Поэтому: первый раз хост
# проверяется честно, и ЕСЛИ он потребовал второго захода — дальше к нему идём сразу без
# проверки, записывая это в `kak` как обычно. Провенанс не страдает: путь получения виден.
_bez_proverki_hosty = set()

OBYCHNO = 'обычно'
BEZ_PROVERKI = 'без проверки сертификата'
NE_OTKRYLSYA = 'сайт не открылся'


def _odin_zahod(url, js, after_ms, bez_proverki, timeout):
    zad = {'url': url, 'proxy': '', 'screenshot': False,
           'eval_js': {'script': js, 'after_ms': after_ms, 'return': 'window.__RES'}}
    if bez_proverki:
        zad['ignore_https_errors'] = True
    try:
        p = subprocess.run([sys.executable, KLIENT, 'browser_probe',
                            json.dumps(zad, ensure_ascii=False)],
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, 'таймаут раннера'
    try:
        otvet = json.loads(p.stdout[p.stdout.index('{'):])
    except (ValueError, json.JSONDecodeError):
        return None, (p.stdout or p.stderr)[-160:]
    d = otvet.get('data') or {}
    if d.get('eval_js_err'):
        return None, str(d['eval_js_err'])[:160]
    try:
        return json.loads(d.get('eval_js_value') or 'null'), ''
    except json.JSONDecodeError as e:
        return None, f'ответ не разобран: {str(e)[:80]}'


def doshli(res):
    """Дошли ли до самого сайта. Признак не про текст ошибки: браузер, оставшийся на заглушке,
    отдаёт `location.origin` строкой "null".

    ДЛЯ СПИСКА СТРАНИЦ НЕПУСТОТА НИЧЕГО НЕ ЗНАЧИТ — и на этом канал терял целые предприятия.
    Разбор страниц возвращает по записи на каждый адрес, и у неудачи запись тоже есть: там
    вместо текста лежит `err`. Список из двадцати ошибок непустой, `bool(res)` даёт True,
    ходок решает «дошли» и ВТОРОГО ЗАХОДА С СЕРТИФИКАТОМ НЕ ДЕЛАЕТ. Поймано числом:
    `uacrussia.ru` и `alrosa.ru` — 20 страниц запрошено, 0 ответили, оба сайта на корне НУЦ
    Минцифры. Это ОАК и АЛРОСА, 9-е и 12-е места по сумме покупок.
    Считается дошедшим список, где хоть у одной записи есть содержимое."""
    if res is None:
        return False
    if isinstance(res, dict):
        return (res.get('origin') or 'null') != 'null'
    if isinstance(res, list):
        return any(isinstance(x, dict) and x.get('t') for x in res)
    return bool(res)


def vzyat(url, js, after_ms=2500, timeout=900):
    """→ (результат, kak, ошибка). `kak` — часть провенанса, а не отладочный вывод."""
    try:
        host = url.split('//', 1)[-1].split('/')[0].lower()
    except Exception:  # noqa: BLE001
        host = ''
    if host in _bez_proverki_hosty:
        res, err = _odin_zahod(url, js, after_ms, True, timeout)
        if doshli(res):
            return res, BEZ_PROVERKI, ''
        return res, NE_OTKRYLSYA, err or 'не дошли и без проверки'
    res, err = _odin_zahod(url, js, after_ms, False, timeout)
    if doshli(res):
        return res, OBYCHNO, ''
    res2, err2 = _odin_zahod(url, js, after_ms, True, timeout)
    if doshli(res2):
        if host:
            _bez_proverki_hosty.add(host)
        return res2, BEZ_PROVERKI, ''
    # Ни так, ни так. Возвращаем ПЕРВЫЙ ответ: он честнее — снят без отключённых проверок.
    return (res if res is not None else res2), NE_OTKRYLSYA, (err or err2 or 'оба захода не дошли')


def dopisyvat(put, cols):
    """Открыть файл на дописывание, СВЕРИВ шапку с текущим списком колонок. Не гадает.

    Зачем. Я добавил модулю колонку `kak`, а файл уже существовал: `DictWriter` продолжил
    дописывать строки по СЕМИ полям в файл с шапкой из ШЕСТИ. Данные не терялись, но
    `DictReader` читает по шапке — и седьмое значение уходило в ключ `None`. Проверка
    показывала «kak пуст у всех 473 строк»: выглядело как несработавшая правка, хотя правка
    сработала, а не было видно её.

    ПОЧЕМУ НЕ ПЕРЕНОСИТЬ ПО ПОЗИЦИЯМ. Первая попытка чинить это переносом «лишние значения
    кладём на новые колонки по порядку» — сама испортила бы файл. Колонка `kak` вставлена
    В СЕРЕДИНУ, и у длинной строки позиция 3 означает `kak`, а у короткой — `robots`.
    Отличить их в перемешанном файле нечем. Гадание тут дороже потери: испорченное значение
    выглядит как настоящее.

    Поэтому три честных исхода:
      * шапка совпала            — просто дописываем;
      * шапка старая, но ВСЕ строки её длины — переносим по ИМЕНАМ, новые клетки пустые;
      * строки разной длины      — файл откладывается рядом с суффиксом `.rassoglasovan`,
                                   работа начинается с чистого; число отложенных печатается.
    Возвращает (файл, новый_ли, сколько_перенесено, сколько_отложено)."""
    import csv as _csv
    perenes = otlozheno = 0
    if os.path.exists(put) and os.path.getsize(put) > 0:
        with open(put, encoding='utf-8-sig', newline='') as f:
            staroe = list(_csv.reader(f, delimiter=';'))
        if staroe and staroe[0] != list(cols):
            imena = staroe[0]
            dlinnye = [r for r in staroe[1:] if len(r) != len(imena)]
            if dlinnye:
                zapas = put + '.rassoglasovan'
                os.replace(put, zapas)
                otlozheno = len(staroe) - 1
            else:
                with open(put, 'w', encoding='utf-8-sig', newline='') as f:
                    w = _csv.DictWriter(f, fieldnames=list(cols), delimiter=';',
                                        extrasaction='ignore')
                    w.writeheader()
                    for r in staroe[1:]:
                        d = dict(zip(imena, r))
                        w.writerow({k: d.get(k, '') for k in cols})
                        perenes += 1
    novyy = not os.path.exists(put) or os.path.getsize(put) == 0
    return open(put, 'a', encoding='utf-8-sig', newline=''), novyy, perenes, otlozheno
