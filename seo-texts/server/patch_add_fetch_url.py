# -*- coding: utf-8 -*-
"""Добавляет в раннер задачу `fetch_url`: скачать файл по URL и положить на дроп.

Зачем. Файлохранилище ЕИС (`zakupki.gov.ru/44fz/filestore/...`) недоступно из песочницы
(геоблок) и не берётся браузерным пробником — сервер отдаёт файл как вложение, и Playwright
падает с «Download is starting». Поэтому вложения контрактов (в т.ч. акты приёмки) прочитать
нечем. Эта задача закрывает дыру: сервер качает, кладёт на дроп, сессия забирает и разбирает.

ЧТО ЭТО МЕНЯЕТ В БЕЗОПАСНОСТИ. Раннер до сих пор умел запускать только фиксированные
скрипты с фиксированной логикой. Универсальный загрузчик — это возможность заставить сервер
сходить на произвольный адрес. Поэтому в fetch_url.py заложены ограничители:

  - только схемы http/https, только метод GET;
  - **запрет приватных, loopback и link-local адресов** после разрешения DNS — иначе
    заданием можно достучаться до внутренних служб самого сервера (локальный API дельфина
    на 127.0.0.1, панель, раннер) и до сети владельца;
  - потолок размера (по умолчанию 60 МБ) и таймаут;
  - файл никуда не пишется, кроме временного каталога и дропа;
  - вызов по-прежнему требует HMAC-подписи задания — кто не знает JOB_SECRET, вызвать не может.

Установка (на сервере владельца):
    C:\\Program Files\\Python311\\python.exe C:\\sender\\server\\patch_add_fetch_url.py
    nssm restart rusprom-runner        <- ОБЯЗАТЕЛЬНО: job_runner.py читается при старте службы

Откат: удалить строку 'fetch_url' из ALLOW в job_runner.py (бэкап рядом) и перезапустить службу.
"""
import os
import py_compile
import shutil
import sys
import time

DIR = os.path.dirname(os.path.abspath(__file__))
RUNNER = os.environ.get('RUNNER_PATH', os.path.join(DIR, 'job_runner.py'))
TARGET = os.environ.get('FETCH_PATH', os.path.join(DIR, 'fetch_url.py'))

ALLOW_ANCHOR = "\nALLOW = {"
ALLOW_LINE = "    'fetch_url': [sys.executable, os.path.join(DIR, 'fetch_url.py')],"

FETCH_SRC = r'''# -*- coding: utf-8 -*-
"""Задача раннера: скачать файл по URL с РФ-IP сервера и положить на файлообменник.

stdin:  {"url": "...", "name": "имя-на-дропе.pdf" (опц.), "max_mb": 60 (опц.),
         "timeout": 90 (опц.)}
stdout: {"ok", "url", "http_status", "content_type", "bytes", "sha256", "drop_name", "error"?}

Ограничители (см. комментарий в patch_add_fetch_url.py):
  - только http/https и только GET;
  - адрес назначения резолвится и проверяется: приватные, loopback, link-local и
    multicast диапазоны запрещены;
  - потолок размера, таймаут;
  - пишет только во временный файл и на дроп.
"""
import hashlib
import ipaddress
import json
import os
import re
import socket
import sys
import tempfile
import urllib.parse
import urllib.request

DROP_URL = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/')
DROP_TOKEN = os.environ.get('DROP_TOKEN', '')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')


def _check_host(host):
    """Разрешить только публичные адреса. Возвращает None или текст ошибки."""
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception as e:  # noqa: BLE001
        return f'DNS не разрешился: {str(e)[:60]}'
    for inf in infos:
        ip = ipaddress.ip_address(inf[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_multicast or ip.is_reserved or ip.is_unspecified):
            return f'адрес {ip} непубличный — запрещено'
    return None


def _drop_up(name, data):
    req = urllib.request.Request(f'{DROP_URL}/{urllib.parse.quote(name)}', data=data,
                                 method='PUT', headers={'X-Drop-Token': DROP_TOKEN})
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read()[:200].decode('utf-8', 'replace')


def main():
    try:
        args = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        args = {}
    out = {'ok': False}
    url = (args.get('url') or '').strip()
    out['url'] = url
    p = urllib.parse.urlsplit(url)
    if p.scheme not in ('http', 'https'):
        out['error'] = 'разрешены только http и https'
        json.dump(out, sys.stdout, ensure_ascii=False)
        return
    bad = _check_host(p.hostname or '')
    if bad:
        out['error'] = bad
        json.dump(out, sys.stdout, ensure_ascii=False)
        return

    max_bytes = int(args.get('max_mb', 60)) * 1024 * 1024
    timeout = int(args.get('timeout', 90))
    req = urllib.request.Request(url, headers={'User-Agent': UA}, method='GET')
    tmp = None
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out['http_status'] = r.status
            out['content_type'] = r.headers.get('Content-Type', '')
            cd = r.headers.get('Content-Disposition', '') or ''
            h = hashlib.sha256()
            total = 0
            fd, tmp = tempfile.mkstemp(prefix='fetch_', suffix='.bin')
            with os.fdopen(fd, 'wb') as f:
                while True:
                    chunk = r.read(65536)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        out['error'] = f'превышен потолок {max_bytes} байт'
                        json.dump(out, sys.stdout, ensure_ascii=False)
                        return
                    h.update(chunk)
                    f.write(chunk)
            out['bytes'] = total
            out['sha256'] = h.hexdigest()
        name = args.get('name')
        if not name:
            m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)', cd)
            name = m.group(1) if m else (os.path.basename(p.path) or 'fetched.bin')
        name = re.sub(r'[^A-Za-z0-9._\-]+', '_', name)[:120] or 'fetched.bin'
        if '.' not in name:
            name += '.bin'
        with open(tmp, 'rb') as f:
            _drop_up(name, f.read())
        out['drop_name'] = name
        out['ok'] = True
    except Exception as e:  # noqa: BLE001
        out['error'] = f'{type(e).__name__}: {str(e)[:160]}'
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:  # noqa: BLE001
                pass
    json.dump(out, sys.stdout, ensure_ascii=False)


if __name__ == '__main__':
    main()
'''


def main():
    # 1) положить сам скрипт задачи
    if os.path.exists(TARGET):
        print(f'{TARGET} уже есть — перезаписываю')
    with open(TARGET, 'w', encoding='utf-8') as f:
        f.write(FETCH_SRC)
    try:
        py_compile.compile(TARGET, doraise=True)
    except Exception as e:  # noqa: BLE001
        sys.exit(f'fetch_url.py не компилируется: {e}')
    print(f'записан {TARGET}')

    # 2) добавить в белый список раннера
    if not os.path.exists(RUNNER):
        sys.exit(f'не найден {RUNNER} (переопредели через RUNNER_PATH)')
    t = open(RUNNER, encoding='utf-8').read()
    if "'fetch_url'" in t:
        print('fetch_url уже в ALLOW, job_runner не трогаю')
    else:
        if t.count(ALLOW_ANCHOR) != 1:
            sys.exit(f'якорь ALLOW найден {t.count(ALLOW_ANCHOR)} раз — отказ')
        bak = f'{RUNNER}.bak-{int(time.time())}'
        shutil.copy2(RUNNER, bak)
        t = t.replace(ALLOW_ANCHOR, ALLOW_ANCHOR + '\n' + ALLOW_LINE, 1)
        open(RUNNER, 'w', encoding='utf-8').write(t)
        try:
            py_compile.compile(RUNNER, doraise=True)
        except Exception as e:  # noqa: BLE001
            shutil.copy2(bak, RUNNER)
            sys.exit(f'ОШИБКА КОМПИЛЯЦИИ job_runner, откачен из {bak}: {e}')
        print(f'fetch_url добавлен в ALLOW (бэкап {bak})')

    print('\nТЕПЕРЬ ОБЯЗАТЕЛЬНО: nssm restart rusprom-runner')
    print('(job_runner.py читается при старте службы, без перезапуска задача не появится)')


if __name__ == '__main__':
    main()
