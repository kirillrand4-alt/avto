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
    """Дошли ли до самого сайта. Признак один и он не про текст ошибки: браузер, оставшийся
    на заглушке, отдаёт `location.origin` строкой "null"."""
    if res is None:
        return False
    if isinstance(res, dict):
        return (res.get('origin') or 'null') != 'null'
    return bool(res)


def vzyat(url, js, after_ms=2500, timeout=900):
    """→ (результат, kak, ошибка). `kak` — часть провенанса, а не отладочный вывод."""
    res, err = _odin_zahod(url, js, after_ms, False, timeout)
    if doshli(res):
        return res, OBYCHNO, ''
    res2, err2 = _odin_zahod(url, js, after_ms, True, timeout)
    if doshli(res2):
        return res2, BEZ_PROVERKI, ''
    # Ни так, ни так. Возвращаем ПЕРВЫЙ ответ: он честнее — снят без отключённых проверок.
    return (res if res is not None else res2), NE_OTKRYLSYA, (err or err2 or 'оба захода не дошли')
