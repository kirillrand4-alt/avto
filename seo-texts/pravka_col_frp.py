# -*- coding: utf-8 -*-
"""ГОТОВАЯ правка col_frp в C:\\sender\\server\\news_scan.py. НЕ ПРИМЕНЕНА.

ПОЧЕМУ НЕ ПРИМЕНЕНА. Этот файл правит рабочий модуль боевого конвейера владельца:
news_scan.py на 1866 строк, из которого ходят все коллекторы, и которым пользуются
параллельные сессии. Такую правку должен разрешить человек, а не согласовать
переписка между агентами. Скрипт написан, проверен на синтаксис и готов к запуску
одной командой; решение о запуске оставляю владельцу.

ЧТО ОН ЧИНИТ. В col_frp стоит

    html, method, meta = (VC._fetch(path) if hasattr(VC, '_fetch') else ...)
    if not html or (isinstance(meta, dict) and meta.get('captcha_type')):
        continue

Отказ хоста ТИХО превращается в пустой список, и 503 неотличим от «новостей нет».
Замер 16.09.2026 на живом сервере показывает, что отказ этот массовый:

    постраничный список ?PAGEN_1=1..14 .... 503 на ВСЕХ 14 страницах
    70 карточек подряд с паузой 1,5 с ..... 503 на 61, 200 на 8, 404 на 1
    150 карточек подряд без пауз .......... 200 на 31, не открылось 119
    одиночная /press-tsentr/novosti/ ...... 200 стабильно

При этом проверено, что ноль col_frp НЕ от дедупа (из 6 новостей страницы в
seen_news нет ни одной при 139 030 ключах) и НЕ от фильтра (логика коллектора на
живой странице даёт 6 элементов из 6). Остаётся молчаливый отказ.

ЧТО СТАНЕТ ПОСЛЕ ПРАВКИ:
  - ретрай, три попытки с растущей паузой;
  - счётчик отказов по кодам ответа и по типу капчи;
  - в лог печатается строка
    «[col_frp] страниц запрошено N, отдано 200 у M, отказов {...}, элементов K»,
    а если отказы были - отдельная строка «числа канала ЗАНИЖЕНЫ»;
  - в кортеже путей убран дубль: в исходнике там ДВАЖДЫ стоял один и тот же адрес,
    то есть второй проход не добавлял ничего.

Сбор структурированного реестра сюда намеренно НЕ вносится: он живёт в
seo-texts/rannie_frp.py (режим `reestr`), где есть разбор полей карточки.

ЗАПУСК (когда владелец разрешит):

    python3 seo-texts/zapusk_na_servere.py seo-texts/pravka_col_frp.py

Порядок внутри: бэкап рядом с файлом -> замена -> py_compile -> живой вызов
col_frp. Если py_compile падает, бэкап возвращается на место автоматически.
Повторный запуск безопасен: правка распознаёт саму себя и не накладывается дважды.
"""
import importlib
import os
import py_compile
import re
import shutil
import sys
import time

PUT = r'C:\sender\server\news_scan.py'
METKA = 'страниц запрошено'          # по ней узнаём, что правка уже наложена

NOVAYA = '''
def col_frp(days, max_items):
    """Тир-2: ФРП (frprf.ru), новости о займах и проектах. Правка 16.09.2026.

    БЫЛО: `if not html: continue` - отказ хоста тихо превращался в пустой список,
    и 503 от DDoS-Guard был неотличим от «новостей нет».
    СТАЛО: ретрай с растущей паузой, счётчик отказов и строка итога в лог.
    Пока отказы не ноль, числа канала ЗАНИЖЕНЫ, и теперь это видно.
    """
    import time as _t
    items = []
    stat = {'zapros': 0, 'ok': 0, 'otkaz': {}}

    def _vzyat(path, popytok=3, pauza=3.0):
        for popytka in range(popytok):
            stat['zapros'] += 1
            if popytka:
                _t.sleep(pauza * (popytka + 1))
            try:
                html, method, meta = (VC._fetch(path) if hasattr(VC, '_fetch')
                                      else (_get(path), 'direct', {}))
            except Exception as e:  # noqa: BLE001
                klyuch = type(e).__name__
                stat['otkaz'][klyuch] = stat['otkaz'].get(klyuch, 0) + 1
                continue
            meta = meta if isinstance(meta, dict) else {}
            kapcha = meta.get('captcha_type')
            if html and not kapcha:
                stat['ok'] += 1
                return html
            klyuch = kapcha or meta.get('http_status') or 'пусто'
            stat['otkaz'][klyuch] = stat['otkaz'].get(klyuch, 0) + 1
        return None

    for path in ('https://frprf.ru/press-tsentr/novosti/',):
        html = _vzyat(path)
        if not html:
            continue
        for m in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.S):
            href, txt = m[0], re.sub(r'<[^>]+>', ' ', m[1]).strip()
            if len(txt) > 25 and any(w in txt.lower() for w in
                                     ('завод', 'цех', 'производств', 'линию', 'займ',
                                      'проект', 'млн', 'млрд')):
                link = href if href.startswith('http') else 'https://frprf.ru' + href
                items.append({'title': txt[:200], 'link': link, 'pubDate': '',
                              'source': 'ФРП', 'tier': 2, 'collector': 'frp'})
            if len(items) >= max_items:
                break
        if items:
            break

    otkaz = ', '.join('%s: %d' % (k, v) for k, v in stat['otkaz'].items()) or 'нет'
    print('[col_frp] страниц запрошено %d, отдано 200 у %d, отказов {%s}, элементов %d'
          % (stat['zapros'], stat['ok'], otkaz, len(items)))
    if stat['otkaz']:
        print('[col_frp] ВНИМАНИЕ: отказы хоста были, числа канала ЗАНИЖЕНЫ. '
              'Это заслон DDoS-Guard, а не пустота в источнике')
    return items
'''


def main():
    if not os.path.exists(PUT):
        print('НЕТ ФАЙЛА:', PUT)
        return 1
    src = open(PUT, encoding='utf-8').read()
    m = re.search(r'\ndef col_frp\(.*?(?=\n(?:def |class |# ))', src, re.S)
    if not m:
        print('col_frp не найдена, ничего не трогаю')
        return 1
    staroe = m.group(0)
    print('col_frp найдена, знаков %d' % len(staroe))
    if METKA in staroe:
        print('правка УЖЕ наложена, второй раз не накладываю')
        return 0

    bak = PUT + '.bak-%s' % time.strftime('%Y%m%d-%H%M%S')
    shutil.copy2(PUT, bak)
    print('бэкап:', bak, os.path.getsize(bak), 'байт')

    novyy = src.replace(staroe, NOVAYA)
    if novyy == src:
        print('замена не сработала, файл не тронут')
        return 1
    open(PUT, 'w', encoding='utf-8').write(novyy)
    try:
        py_compile.compile(PUT, doraise=True)
        print('py_compile: ок')
    except Exception as e:  # noqa: BLE001
        shutil.copy2(bak, PUT)
        print('py_compile УПАЛ, бэкап возвращён:', type(e).__name__, str(e)[:200])
        return 1

    sys.path.insert(0, r'C:\sender\server')
    sys.modules.pop('news_scan', None)
    try:
        NS = importlib.import_module('news_scan')
        el = NS.col_frp(7, 30)
        print('ЖИВОЙ ВЫЗОВ col_frp: элементов %d' % len(el))
        for it in el[:5]:
            print('   ', it['title'][:80])
        # КОНТРОЛЬ с заведомо негодным входом: потолок 0 обязан дать 0 элементов
        print('КОНТРОЛЬ max_items=0: элементов %d (обязан быть 0)' % len(NS.col_frp(7, 0)))
    except Exception as e:  # noqa: BLE001
        print('живой вызов упал:', type(e).__name__, str(e)[:300])
        print('py_compile прошёл, файл оставлен исправленным. Откат:', bak)
        return 1
    print('ГОТОВО. Откатить при необходимости копированием', bak, '->', PUT)
    return 0


if __name__ == '__main__':
    sys.exit(main())
