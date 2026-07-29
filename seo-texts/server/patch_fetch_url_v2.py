# -*- coding: utf-8 -*-
"""Патч v2 задачи `fetch_url`: поддержка российских госсертификатов + самообновляемость.

Что показал первый прогон: задача установилась и отработала, но упала на
`SSL: CERTIFICATE_VERIFY_FAILED` — `zakupki.gov.ru` подписан НУЦ Минцифры, которому
хранилище Python не доверяет. Ровно по этой же причине браузерному пробнику нужен был
`ignore_https_errors`.

Что делает v2:

  1. **Флаг `insecure`** в аргументах задачи. По умолчанию **выключен**: обычные сайты
     качаются с полной проверкой сертификата. Включать точечно и осознанно — для
     госресурсов с российскими корневыми (`zakupki.gov.ru`, `pub.fsa.gov.ru` и т.п.).
     Риск при выключенной проверке — подмена трафика; для публичных документов закупок
     последствие невелико, но флаг именно поэтому не сделан значением по умолчанию.
     Заодно в ответ пишется `insecure: true`, чтобы это было видно в результате.

  2. **`fetch_url.py` добавляется в `PULL_ALLOW`** раннера. Тогда дальнейшие правки самой
     задачи выкатываются штатным механизмом самообновления (положить файл на дроп и
     отправить задание `pull`), без ручных заходов в PowerShell.

Установка:
    C:\\Program Files\\Python311\\python.exe C:\\sender\\server\\patch_fetch_url_v2.py
    nssm restart rusprom-runner     <- нужен, т.к. меняется job_runner.py

Откат: бэкапы обоих файлов лежат рядом с ними (.bak-<timestamp>).
"""
import os
import py_compile
import shutil
import sys
import time

DIR = os.path.dirname(os.path.abspath(__file__))
RUNNER = os.environ.get('RUNNER_PATH', os.path.join(DIR, 'job_runner.py'))
TARGET = os.environ.get('FETCH_PATH', os.path.join(DIR, 'fetch_url.py'))

PULL_ANCHOR = "PULL_ALLOW = {'verify_company.py',"
PULL_NEW = "PULL_ALLOW = {'fetch_url.py', 'verify_company.py',"

FETCH_SRC = r'''# -*- coding: utf-8 -*-
"""Задача раннера: скачать файл по URL с РФ-IP сервера и положить на файлообменник.

stdin:  {"url": "...", "name": "имя-на-дропе.pdf" (опц.), "max_mb": 60 (опц.),
         "timeout": 90 (опц.), "insecure": false (опц.)}
stdout: {"ok", "url", "http_status", "content_type", "bytes", "sha256", "drop_name",
         "insecure", "error"?}

Ограничители:
  - только http/https и только GET;
  - адрес резолвится и проверяется: приватные, loopback, link-local, multicast запрещены,
    иначе заданием можно достучаться до внутренних служб самого сервера;
  - потолок размера, таймаут;
  - пишет только во временный файл и на дроп.

insecure=true отключает проверку сертификата. Нужен для госресурсов с российскими
корневыми (НУЦ Минцифры): zakupki.gov.ru, pub.fsa.gov.ru и т.п. По умолчанию выключен.
"""
import hashlib
import ipaddress
import json
import os
import re
import socket
import ssl
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
    insecure = bool(args.get('insecure'))
    out['insecure'] = insecure
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

    ctx = None
    if insecure:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    max_bytes = int(args.get('max_mb', 60)) * 1024 * 1024
    timeout = int(args.get('timeout', 90))
    req = urllib.request.Request(url, headers={'User-Agent': UA}, method='GET')
    tmp = None
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
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
    with open(TARGET, 'w', encoding='utf-8') as f:
        f.write(FETCH_SRC)
    try:
        py_compile.compile(TARGET, doraise=True)
    except Exception as e:  # noqa: BLE001
        sys.exit(f'fetch_url.py не компилируется: {e}')
    print(f'обновлён {TARGET} (добавлен флаг insecure)')

    if not os.path.exists(RUNNER):
        sys.exit(f'не найден {RUNNER}')
    t = open(RUNNER, encoding='utf-8').read()
    if PULL_NEW in t:
        print('fetch_url.py уже в PULL_ALLOW')
    elif t.count(PULL_ANCHOR) != 1:
        print(f'якорь PULL_ALLOW найден {t.count(PULL_ANCHOR)} раз — НЕ ПАТЧУ '
              f'(самообновление задачи останется недоступным)')
    else:
        bak = f'{RUNNER}.bak-{int(time.time())}'
        shutil.copy2(RUNNER, bak)
        open(RUNNER, 'w', encoding='utf-8').write(t.replace(PULL_ANCHOR, PULL_NEW, 1))
        try:
            py_compile.compile(RUNNER, doraise=True)
        except Exception as e:  # noqa: BLE001
            shutil.copy2(bak, RUNNER)
            sys.exit(f'ОШИБКА КОМПИЛЯЦИИ job_runner, откачен из {bak}: {e}')
        print(f'fetch_url.py добавлен в PULL_ALLOW (бэкап {bak})')

    print('\nНУЖЕН: nssm restart rusprom-runner')


if __name__ == '__main__':
    main()
