# -*- coding: utf-8 -*-
"""Выкатка panel-update.zip на сервере в обход hairpin-NAT.

ЗАЧЕМ. Штатный op `panel_zip_deploy` (enrich_contacts.py) качает пакет с дропа
одним GET и на пакете 825 КБ стабильно падает:
    IncompleteRead(311296 bytes read, 513666 more expected)
Причина известна и записана в самом enrich_contacts.py (ветка inline-b64 в
`panel_file_put`): сервер ходит на СВОЙ публичный адрес, hairpin-NAT рвёт
ответ примерно на 384 КБ. Мелкие файлы проезжают, пакет панели — нет.

ОБХОД, способ 1 (основной): HTTP не нужен вовсе. Хранилище дропа лежит на ЭТОМ
же сервере — `C:\seostat\drop\drop-storage` (тот же путь берут
`enrich_contacts._read_secret` для runner-secrets.env и `_ops_pull_obzvon.py`).
Пакет просто копируется с диска: ни домена, ни NAT, ни лимита.

ОБХОД, способ 2 (запасной, если хранилище переедет): лимит действует на размер
ОДНОГО ответа, поэтому качаем Range-запросами по 256 КБ — каждый ответ заведомо
меньше порога. Дроп это умеет: `drop_server.download` отдаёт файл через
`send_from_directory`, а он поддерживает Range.

Целостность в обоих случаях проверяем по размеру, sha256 и zipfile.testzip.

Дальше повторяем семантику update-panel.ps1, включая АВТО-ОТКАТ: бэкап →
стоп службы → распаковка → старт → проверка живости. Живой ответ — любой,
кроме 5xx: 401/403 у панели это штатная Basic-авторизация, а не падение
(инцидент 26.07: скрипт принял 401 за отказ и откатил рабочую выкатку).
Дополнительно сверяем, что index.html ссылается на реально лежащие ассеты —
на рассинхроне index.html и assets панель ложилась белым экраном.

Запуск (через op panel_py, argv):
    python _ops_panel_deploy.py fetch [имя_на_дропе] [ожид_размер] [ожид_sha256]
    python _ops_panel_deploy.py apply [имя_на_дропе] [служба]
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile

SENDER = r'C:\sender'
DIST = os.path.join(SENDER, 'web', 'dist')
CHUNK = 256 * 1024          # заведомо ниже порога hairpin-NAT (~384 КБ)
TRIES = 4


def _nssm():
    n = shutil.which('nssm')
    if n:
        return n
    for c in (r'C:\nssm.exe', r'C:\nssm\nssm.exe', r'C:\nssm\win64\nssm.exe',
              r'C:\tools\nssm\nssm.exe', r'C:\nssm-2.24\win64\nssm.exe'):
        if os.path.exists(c):
            return c
    return None


def _svc(action, service):
    n = _nssm()
    if not n:
        return 'нет nssm'
    p = subprocess.run([n, action, service], capture_output=True, timeout=90)
    raw = (p.stdout or b'') + (p.stderr or b'')
    try:
        t = raw.decode('utf-16-le') if b'\x00' in raw[:8] else raw.decode('utf-8', 'replace')
    except Exception:  # noqa: BLE001
        t = raw.decode('utf-8', 'replace')
    return t.strip()[:200]


def _url(name):
    base = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop')
    return base.rstrip('/') + '/' + name


def _headers(extra=None):
    h = {'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}
    h.update(extra or {})
    return h


def _total_size(name):
    """Длина файла на дропе. HEAD у Flask отвечает как GET без тела, но на
    hairpin это тоже риск, поэтому спрашиваем первым Range-запросом."""
    req = urllib.request.Request(_url(name), headers=_headers({'Range': 'bytes=0-0'}))
    with urllib.request.urlopen(req, timeout=60) as r:
        cr = r.headers.get('Content-Range') or ''
        if r.status == 206 and '/' in cr:
            return int(cr.rsplit('/', 1)[1]), True
        # Range не поддержан — придётся одним куском (и, вероятно, оборвётся)
        return int(r.headers.get('Content-Length') or 0), False


def _local_drop(name):
    """Путь к файлу в ЛОКАЛЬНОМ хранилище дропа, если оно на этой машине."""
    for base in (os.environ.get('DROP_DIR') or '',
                 r'C:\seostat\drop\drop-storage'):
        if base:
            p = os.path.join(base, name)
            if os.path.exists(p):
                return p
    return None


def fetch(name, expect_size=0, expect_sha=''):
    out = {'шаг': 'fetch', 'файл': name}

    # Способ 1: файл лежит на этом же диске — HTTP не нужен.
    local = _local_drop(name)
    if local:
        out['источник'] = f'локальное хранилище дропа ({local})'
        blob = open(local, 'rb').read()
        return _finish(out, name, blob, expect_size, expect_sha)

    out['источник'] = 'HTTP Range (локального хранилища не видно)'
    total, ranged = _total_size(name)
    out['размер_на_дропе'], out['range'] = total, ranged
    if not total:
        out['итог'] = 'дроп не отдал размер'
        return out
    dst = os.path.join(SENDER, name)
    buf = bytearray()
    got = 0
    while got < total:
        end = min(got + CHUNK, total) - 1
        for t in range(1, TRIES + 1):
            try:
                req = urllib.request.Request(
                    _url(name), headers=_headers({'Range': f'bytes={got}-{end}'}))
                with urllib.request.urlopen(req, timeout=120) as r:
                    part = r.read()
                if len(part) != end - got + 1:
                    raise IOError(f'кусок {got}-{end}: пришло {len(part)}')
                buf += part
                got += len(part)
                break
            except Exception as e:  # noqa: BLE001
                if t == TRIES:
                    out['итог'] = f'кусок {got}-{end} не дошёл: {str(e)[:120]}'
                    out['скачано'] = got
                    return out
                time.sleep(1.5 * t)
    return _finish(out, name, bytes(buf), expect_size, expect_sha)


def _finish(out, name, blob, expect_size, expect_sha):
    """Проверка целостности и запись пакета — общая для обоих способов."""
    dst = os.path.join(SENDER, name)
    out['получено'] = len(blob)
    sha = hashlib.sha256(blob).hexdigest()
    out['sha256'] = sha
    if expect_size and int(expect_size) != len(blob):
        out['итог'] = f'размер не сошёлся: ждали {expect_size}, взяли {len(blob)}'
        return out
    if expect_sha and expect_sha != sha:
        out['итог'] = 'sha256 не сошёлся — файл побился в пути'
        return out
    with open(dst, 'wb') as f:
        f.write(blob)
    if not zipfile.is_zipfile(dst):
        out['итог'] = 'полученное не zip'
        return out
    with zipfile.ZipFile(dst) as z:
        bad = z.testzip()
        out['записей'] = len(z.namelist())
    out['итог'] = 'ГОТОВО' if bad is None else f'битая запись в zip: {bad}'
    return out


def _refs_ok(dist):
    ih = os.path.join(dist, 'index.html')
    if not os.path.exists(ih):
        return False, ['нет index.html']
    html = open(ih, encoding='utf-8', errors='replace').read()
    refs = sorted(set(re.findall(r'/assets/[A-Za-z0-9._-]+', html)))
    bad = [r for r in refs
           if not os.path.exists(os.path.join(dist, r.lstrip('/').replace('/', os.sep)))]
    return (not bad), (bad or refs)


def _alive():
    """Живость панели: успех — любой ответ, кроме 5xx. 401/403 штатны."""
    try:
        req = urllib.request.Request('http://127.0.0.1:8091/', method='GET')
        with urllib.request.urlopen(req, timeout=15) as r:
            return True, r.status
    except urllib.error.HTTPError as e:
        return (e.code < 500), e.code
    except Exception as e:  # noqa: BLE001
        return False, str(e)[:80]


def apply_(name, service='SenderPanel'):
    out = {'шаг': 'apply', 'служба': service}
    zpath = os.path.join(SENDER, name)
    if not os.path.exists(zpath) or not zipfile.is_zipfile(zpath):
        out['итог'] = f'нет валидного пакета {zpath} — сперва fetch'
        return out
    with zipfile.ZipFile(zpath) as z:
        names = z.namelist()
        for nm in names:
            if '..' in nm or nm.startswith(('/', '\\')):
                out['итог'] = f'подозрительный путь в zip: {nm}'
                return out
    ts = str(int(time.time()))
    bak_root = os.path.join(SENDER, '_bak-' + ts)
    for sub in ('sender', os.path.join('web', 'dist')):
        src = os.path.join(SENDER, sub)
        if os.path.exists(src):
            shutil.copytree(src, os.path.join(bak_root, sub.replace(os.sep, '_')))
    out['бэкап'] = bak_root

    out['stop'] = _svc('stop', service)
    time.sleep(3)
    with zipfile.ZipFile(zpath) as z:
        z.extractall(SENDER)
    out['распаковано'] = len(names)
    _svc('start', service)
    time.sleep(6)

    ok_refs, refs = _refs_ok(DIST)
    ok_http, code = _alive()
    out['ссылки_целы'], out['ссылки'] = ok_refs, refs
    out['http'] = code
    if ok_refs and ok_http:
        out['статус_службы'] = _svc('status', service)
        out['итог'] = 'ГОТОВО'
        return out

    # авто-откат
    _svc('stop', service)
    time.sleep(2)
    for sub in ('sender', os.path.join('web', 'dist')):
        b = os.path.join(bak_root, sub.replace(os.sep, '_'))
        dst = os.path.join(SENDER, sub)
        if os.path.exists(b):
            shutil.rmtree(dst, ignore_errors=True)
            shutil.copytree(b, dst)
    _svc('start', service)
    time.sleep(6)
    out['откат'] = True
    out['после_отката'] = _alive()[1]
    out['итог'] = 'ВЫКАТКА НЕ ПРОШЛА — откатились из бэкапа'
    return out


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'fetch'
    name = os.path.basename(sys.argv[2]) if len(sys.argv) > 2 else 'panel-update.zip'
    if cmd == 'fetch':
        size = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        sha = sys.argv[4] if len(sys.argv) > 4 else ''
        res = fetch(name, size, sha)
    elif cmd == 'apply':
        res = apply_(name, sys.argv[3] if len(sys.argv) > 3 else 'SenderPanel')
    else:
        res = {'итог': f'неизвестная команда {cmd}'}
    print(json.dumps(res, ensure_ascii=False))


if __name__ == '__main__':
    main()
