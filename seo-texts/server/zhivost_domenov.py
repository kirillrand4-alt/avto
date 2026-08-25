# -*- coding: utf-8 -*-
r"""Проверка живости доменов-кандидатов: что мертво, что припарковано, что жив.

Зачем. Замер 25.08 на 600 компаниях показал: 34% сайтов, доставшихся из базы
обзвона, — мёртвые, припаркованные или молчащие домены, а шесть штук в выборке
перепроданы под казино, и паспорт компании собирается с их страниц. Обход таких
доменов Зенкой — потраченное время потока, а разбор — потраченные деньги
провайдера. Дешевле узнать заранее.

Как. DNS, потом один HTTP-запрос, потом разбор ответа по признакам парковки и
подмены. Вердикт на компанию пишется в prigovor_domenov — таблицу, где такие
приговоры уже живут.

Резюмируемость. Прогон долгий и идёт отдельным процессом, поэтому переживает
и таймаут задания, и рестарт песочницы: сделанное лежит в серверном jsonl с
fsync, и повторный запуск продолжает с того места, а не начинает заново.

Запуск (на сервере, отдельным процессом):
    python zhivost_domenov.py            # весь остаток
    python zhivost_domenov.py --predel N # только N штук, для пробы
"""
import io
import json
import os
import re
import socket
import sqlite3
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

БД = r'C:\sender\enrich.db'
ВЫХОД = r'C:\sender\zhivost-domenov.jsonl'
ЖУРНАЛ = r'C:\sender\zhivost-domenov.log'
ИСТОЧНИК = 'обзвон:понижен-25.08'
ПОТОКОВ = int(os.environ.get('ZHIVOST_POTOKOV', '24'))
ТАЙМАУТ = 12

# Признаки парковки — только те, что стоят в ТЕКСТЕ страницы-заглушки. Слово
# «parking» в пути картинки не в счёт: у автосервисов это товар, а не заглушка.
_ПАРКОВКА = re.compile(
    r'домен(?:ное имя)? (?:продаётся|продается|припаркован)|этот домен продается|'
    r'this domain (?:is )?(?:for sale|has expired)|domain (?:is )?parked|'
    r'buy this domain|купить этот домен|срок регистрации домена (?:истёк|истек)|'
    r'sedoparking|parkingcrew|hugedomains|reg\.ru/domain|домен не настроен|'
    r'website coming soon|сайт в разработке|заглушка хостинга', re.I)
# Подмена под игорный ресурс: у доменов, перепроданных после закрытия компании.
_КАЗИНО = re.compile(
    r'казино|casino|букмекер|1xbet|зеркало сайта|игровые автоматы|'
    r'бонус за регистрацию|фриспин', re.I)


def _хост(url):
    т = re.sub(r'^https?://', '', (url or '').strip()).split('/')[0]
    return т.split(':')[0].strip().lower()


def _в_punycode(хост):
    """Кириллический домен → ascii. Без этого .рф-адреса не резолвятся."""
    try:
        хост.encode('ascii')
        return хост
    except UnicodeEncodeError:
        return '.'.join(ч.encode('idna').decode('ascii') for ч in хост.split('.') if ч)


def проверить(строка):
    инн, url = строка
    хост = _хост(url)
    итог = {'inn': инн, 'domen': хост, 'ts': time.strftime('%Y-%m-%dT%H:%M:%S')}
    if not хост:
        итог.update(verdikt='мёртвый', pochemu='адрес пуст')
        return итог
    try:
        ascii_хост = _в_punycode(хост)
    except Exception:
        итог.update(verdikt='мёртвый', pochemu='имя домена не разбирается')
        return итог
    try:
        socket.getaddrinfo(ascii_хост, 80, proto=socket.IPPROTO_TCP)
    except Exception:
        итог.update(verdikt='мёртвый', pochemu='домена нет в DNS')
        return итог
    for схема in ('http://', 'https://'):
        try:
            зпр = urllib.request.Request(
                схема + ascii_хост + '/',
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
            with urllib.request.urlopen(зпр, timeout=ТАЙМАУТ) as о:
                тело = о.read(120000).decode('utf-8', 'replace')
                код = о.getcode()
            if _КАЗИНО.search(тело) and not _ПАРКОВКА.search(тело):
                итог.update(verdikt='подменён', pochemu='игорный ресурс на месте сайта')
            elif _ПАРКОВКА.search(тело):
                итог.update(verdikt='парковка', pochemu='заглушка регистратора/хостера')
            elif len(re.sub(r'<[^>]+>', ' ', тело).strip()) < 200:
                итог.update(verdikt='пустой', pochemu='страница без текста')
            else:
                итог.update(verdikt='жив', pochemu='код %s, знаков %d' % (код, len(тело)))
            return итог
        except urllib.error.HTTPError as e:
            if e.code in (401, 403, 429):     # закрылся от робота — не мёртв
                итог.update(verdikt='жив', pochemu='код %s (закрыт от робота)' % e.code)
                return итог
            итог.update(verdikt='молчит', pochemu='код %s' % e.code)
        except Exception as e:
            итог.update(verdikt='молчит', pochemu=type(e).__name__)
    return итог


def сделанные():
    if not os.path.exists(ВЫХОД):
        return set()
    было = set()
    for s in io.open(ВЫХОД, encoding='utf-8', errors='replace'):
        try:
            было.add(json.loads(s)['inn'])
        except Exception:
            pass
    return было


def лог(текст):
    with io.open(ЖУРНАЛ, 'a', encoding='utf-8') as f:
        f.write('%s %s\n' % (time.strftime('%H:%M:%S'), текст))
        f.flush()
        os.fsync(f.fileno())


def главное(предел=None):
    c = sqlite3.connect('file:%s?mode=ro' % БД.replace('\\', '/'), uri=True, timeout=60)
    все = [(str(r[0]), r[1]) for r in c.execute(
        "select inn, cand_site from companies where site_source=? "
        "and coalesce(cand_site,'')<>''", (ИСТОЧНИК,))]
    c.close()
    было = сделанные()
    работа = [x for x in все if x[0] not in было]
    if предел:
        работа = работа[:предел]
    лог('старт: всего %d, сделано %d, к работе %d' % (len(все), len(было), len(работа)))

    буфер, сделано, т0 = [], 0, time.time()
    with ThreadPoolExecutor(max_workers=ПОТОКОВ) as ex:
        for итог in ex.map(проверить, работа):
            буфер.append(итог)
            сделано += 1
            if len(буфер) >= 100:
                _сброс(буфер)
                буфер = []
                лог('сделано %d из %d, темп %.0f/мин' % (
                    сделано, len(работа), сделано / max(1e-9, (time.time() - т0)) * 60))
    if буфер:
        _сброс(буфер)
    _в_bd()
    лог('готово: %d за %d мин' % (сделано, round((time.time() - т0) / 60)))


def _сброс(буфер):
    with io.open(ВЫХОД, 'a', encoding='utf-8') as f:
        for э in буфер:
            f.write(json.dumps(э, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())


def _в_bd():
    """Вердикты в prigovor_domenov пачками — по базе параллельно пишут другие."""
    строки = []
    for s in io.open(ВЫХОД, encoding='utf-8', errors='replace'):
        try:
            строки.append(json.loads(s))
        except Exception:
            pass
    # По базе параллельно идут проход по ролям и разбор паспортов, и своей
    # пачки можно не дождаться. Терять из-за этого работу нельзя: сканирование
    # уже лежит в jsonl, поэтому пачка просто ждёт своей очереди и пробует
    # снова, а не роняет прогон. Не легло за все попытки — выходим с честным
    # сообщением, файл цел, запись повторяется отдельным запуском --v-bazu.
    c = sqlite3.connect(БД, timeout=120)
    c.execute('PRAGMA busy_timeout=60000')
    порция, легло, не_легло = 500, 0, 0
    for i in range(0, len(строки), порция):
        пачка = строки[i:i + порция]
        for попытка in range(6):
            try:
                c.execute('BEGIN IMMEDIATE')
                for э in пачка:
                    c.execute("insert or replace into prigovor_domenov "
                              "(inn, domen, verdikt, pochemu, ts) values (?,?,?,?,?)",
                              (э['inn'], э['domen'], э['verdikt'], э['pochemu'], э['ts']))
                c.commit()
                легло += len(пачка)
                break
            except sqlite3.OperationalError:
                try:
                    c.rollback()
                except Exception:
                    pass
                time.sleep(5 * (попытка + 1))
        else:
            не_легло += len(пачка)
        time.sleep(0.2)
    c.close()
    лог('в базу записано %d вердиктов, не легло %d' % (легло, не_легло))


if __name__ == '__main__':
    if '--v-bazu' in sys.argv:      # только перенос уже собранного в базу
        _в_bd()
        raise SystemExit(0)
    предел = None
    if '--predel' in sys.argv:
        предел = int(sys.argv[sys.argv.index('--predel') + 1])
    главное(предел)
