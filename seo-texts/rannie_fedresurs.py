# -*- coding: utf-8 -*-
"""Ранний источник 2: Федресурс (fedresurs.ru). КАНАЛ НЕ ОТКРЫТ.

Владелец 16.09.2026 велел дойти до диагноза и остановиться: условия доступа он
смотрит сам. Этот файл - не рабочий клиент, а воспроизводимая проба: запусти и
получишь те же коды ответа, что ниже.

    python3 seo-texts/rannie_fedresurs.py          # из песочницы
    python3 seo-texts/zapusk_na_servere.py seo-texts/rannie_fedresurs.py   # с сервера

ДИАГНОЗ (замер 16.09.2026, песочница и сервер владельца дали ОДНО И ТО ЖЕ):

    https://fedresurs.ru/                     401, 1598 байт, server: QRATOR
    https://bankrot.fedresurs.ru/             401, 1598 байт, server: QRATOR
    https://fedresurs.ru/backend/...          403, 548 байт, тело nginx
    https://api.fedresurs.ru/                 хост НЕ РЕЗОЛВИТСЯ (getaddrinfo failed)
    https://fedresurs.ru/robots.txt           200, 373 байта
    https://fedresurs.ru/api, /help/api,
    /about/opendata, /sitemap.xml             200, но все ровно 22 446 байт -
                                              это оболочка Angular-приложения,
                                              один и тот же файл на любой путь

ЧТО ИЗ ЭТОГО СЛЕДУЕТ, по пунктам:

1. ХОСТ ДОСТИЖИМ. 401 и 403 - это ответы. Недоступен только тот, кто не ответил
   вовсе. Закрыт не сайт, закрыт вход.

2. ЗАКРЫТО ВСЁ ПУБЛИЧНОЕ, А НЕ ОТДЕЛЬНЫЙ РАЗДЕЛ. 401 отдаёт и главная
   fedresurs.ru, и bankrot.fedresurs.ru - то есть и публичный поиск сообщений,
   и карточка юрлица, и реестр банкротств. Выгрузку проверить не удалось: до
   неё не доходит, страница не открывается.

3. МАШИННЫЙ ИНТЕРФЕЙС У ПОРТАЛА ЕСТЬ, и он назван самим порталом. robots.txt
   перечисляет закрываемые от индексации адреса, и это ровно эндпоинты API:
       Disallow: /backend/companies/search
       Disallow: /backend/persons/search
       Disallow: /backend/nonresidentcompanies/search
       Disallow: /backend/encumbrances          <- залоги, наш индикатор
       Disallow: /backend/realestate/search
       Disallow: /backend/fnp-search
   То есть искать скрытый API не нужно, он документирован отказным списком.

4. 403 НА /backend/ - ЭТО НЕ QRATOR, А ПРОВЕРКА ЗАГОЛОВКОВ. Голый запрос даёт
   403 nginx (548 байт). Тот же адрес с Referer https://fedresurs.ru/...,
   Origin https://fedresurs.ru и X-Requested-With: XMLHttpRequest даёт уже
   404 с пустым телом - то есть заслон пройден, а путь или имена параметров
   угаданы неверно. Имена параметров надо снимать с фронта, а не угадывать
   (правило: имя поля ответа проверять, а не угадывать). Дальше по указанию
   владельца я не шла.

5. ОФИЦИАЛЬНОГО ОТКРЫТОГО ЭНДПОИНТА НЕТ. api.fedresurs.ru не резолвится ни из
   песочницы, ни с сервера - значит адрес из общих представлений неверен, и
   гадать его нельзя.

ЧТО НУЖНО ОТ ВЛАДЕЛЬЦА, чтобы канал открылся (три РАЗНЫЕ вещи, не путать):

    а) для ЧТЕНИЯ сообщений оптом - договор и ключ доступа к API Федресурса.
       Оператор ЕФРСФДЮЛ - АО «Интерфакс», доступ платный и по договору.
       Это единственный путь, не требующий обхода защиты;
    б) для ПУБЛИКАЦИИ сообщений - квалифицированная электронная подпись.
       Нам не нужна: мы читаем, а не публикуем;
    в) для разовой ручной проверки - обычный браузер с живым российским IP,
       который проходит проверку Qrator. Наши мобильные прокси на это не
       годятся: все три из C:\\sender\\proxies-mobile.txt мертвы
       (WinError 10054 на каждом).

ВЫВОД: НЕ БЕРЁМ без платного доступа. Обходить Qrator не пробовала - владелец
снял задачу.
"""
import sys
import urllib.error
import urllib.request

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

CELI = [
    ('главная портала', 'https://fedresurs.ru/', None),
    ('реестр банкротств', 'https://bankrot.fedresurs.ru/', None),
    ('поиск компаний, голый запрос', 'https://fedresurs.ru/backend/companies/search?query=7702070139', None),
    ('поиск компаний, с заголовками фронта',
     'https://fedresurs.ru/backend/companies/search?searchString=7702070139&limit=15&offset=0',
     {'Accept': 'application/json, text/plain, */*',
      'Referer': 'https://fedresurs.ru/search/entity',
      'Origin': 'https://fedresurs.ru',
      'X-Requested-With': 'XMLHttpRequest'}),
    ('залоги', 'https://fedresurs.ru/backend/encumbrances?limit=15&offset=0', None),
    ('robots.txt', 'https://fedresurs.ru/robots.txt', None),
    ('официальный API', 'https://api.fedresurs.ru/', None),
    # КОНТРОЛЬ с заведомо негодным входом: выдуманный поддомен обязан НЕ ответить
    ('КОНТРОЛЬ выдуманный хост', 'https://shvartskopfer.fedresurs.ru/', None),
]


def proba(url, dop=None):
    zag = {'User-Agent': UA, 'Accept': 'text/html,application/json,*/*;q=0.8',
           'Accept-Language': 'ru-RU,ru;q=0.9'}
    if dop:
        zag.update(dop)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=zag), timeout=30) as f:
            return f.status, len(f.read(200000)), (f.headers.get('Server') or '')
    except urllib.error.HTTPError as e:
        telo = e.read(3000) if e.fp else b''
        return e.code, len(telo), ((e.headers.get('Server') or '') if e.headers else '')
    except Exception as e:  # noqa: BLE001
        return 0, 0, '%s: %s' % (type(e).__name__, str(e)[:70])


def main():
    print('%-38s %-5s %-8s %s' % ('что', 'код', 'байт', 'server / причина'))
    for imya, url, dop in CELI:
        kod, n, srv = proba(url, dop)
        print('%-38s %-5s %-8s %s' % (imya[:38], kod, n, srv[:60]))
    print()
    print('Напоминание: 401 и 403 - это ОТВЕТЫ, хост достигнут. Ноль в колонке кода')
    print('означает, что хост не ответил вовсе, и только это «недоступен».')
    print('Подробный разбор и что нужно от владельца - в шапке этого файла')
    print('и в seo-texts/RANNIE-ISTOCHNIKI-OPIS.md.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
