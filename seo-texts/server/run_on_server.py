# -*- coding: utf-8 -*-
"""Клиент раннера (сторона песочницы Claude): подписать задание, положить на дроп,
дождаться result-<id>.json. Пара к server/job_runner.py на сервере владельца.

Секреты берёт из окружения (DROP_URL/DROP_TOKEN/JOB_SECRET) или из скачанного с
дропа runner-secrets.env. Использование:
    python run_on_server.py verify_company '{"companies":[{"name":"КАО Азот","inn":"4205000908"}]}'
    python run_on_server.py ping '{"hi":1}'
"""
import os
import sys
import json
import time
import hmac
import hashlib
import itertools
import subprocess
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor

DIR = os.path.dirname(os.path.abspath(__file__))
DROP_URL = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/')
DROP_TOKEN = os.environ.get('DROP_TOKEN', '')
JOB_SECRET = os.environ.get('JOB_SECRET', '')


def _load_secret_from_drop():
    """JOB_SECRET из runner-secrets.env на дропе (если в env нет)."""
    global JOB_SECRET
    if JOB_SECRET:
        return
    try:
        blob = _req('GET', 'runner-secrets.env').decode('utf-8', 'replace')
        for line in blob.splitlines():
            if line.strip().startswith('JOB_SECRET='):
                JOB_SECRET = line.split('=', 1)[1].strip()
    except Exception:  # noqa: BLE001
        pass


def _req(method, path, data=None):
    req = urllib.request.Request(f'{DROP_URL}/{path}', data=data, method=method,
                                 headers={'X-Drop-Token': DROP_TOKEN})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read()


_SCHET = itertools.count(1)
_SCHET_LOCK = threading.Lock()


def _now_id():
    """Уникальное имя задания.

    **Здесь была та поломка, из-за которой мы записали «раннер выполняет задания по одному».**
    Прежняя версия возвращала `f'{int(time.time())}-{os.getpid()}'`, то есть два задания,
    отправленные одним процессом в одну и ту же секунду, получали **одинаковое имя** и затирали
    друг друга на дропе: исполнялось одно, остальные исчезали молча. Отсюда вывод «параллельно
    нельзя» и запись в документах.

    Серверная сторона (`job_runner.py`) при этом параллельная с самого начала: общий пул
    `RUNNER_WORKERS=8`, отдельный тяжёлый пул на 1 воркер. Тяжёлым считается задание с
    `sweep`, `mass_base`, `news_enrich`, `xmlriver_queries`, `kg_probe`, а также
    `enrich_contacts` с `companies` и **без** `site_crawl` — вот почему такое задание висит до
    таймаута, когда тяжёлый пул занят.

    То есть мерили клиента, а запрет записали про раннер. Класс ошибки тот же, что дал сегодня
    четыре отмены выводов.
    """
    with _SCHET_LOCK:
        n = next(_SCHET)
    return (f'{int(time.time())}-{os.getpid()}-{threading.get_ident() % 100000}-{n}-'
            f'{os.urandom(3).hex()}')


def submit(task, args, wait=True, poll=15, timeout=1800):
    _load_secret_from_drop()
    jid = _now_id()
    job = {'id': jid, 'task': task, 'args': args, 'ts': int(time.time())}
    canon = json.dumps({'id': job['id'], 'task': job['task'], 'args': job['args'],
                        'ts': job['ts']}, sort_keys=True, separators=(',', ':'),
                       ensure_ascii=False)
    if JOB_SECRET:
        job['sig'] = hmac.new(JOB_SECRET.encode(), canon.encode(),
                              hashlib.sha256).hexdigest()
    _req('PUT', f'job-{jid}.json',
         data=json.dumps(job, ensure_ascii=False).encode('utf-8'))
    print(f'задание отправлено: job-{jid}.json (task={task}, подпись={"да" if JOB_SECRET else "нет"})',
          file=sys.stderr)
    if not wait:
        return {'submitted': jid}
    deadline = time.time() + timeout
    rname = f'result-{jid}.json'
    while time.time() < deadline:
        time.sleep(poll)
        try:
            files = json.loads(_req('GET', 'list'))
        except Exception:  # noqa: BLE001
            continue
        if any(f['name'] == rname for f in files):
            res = json.loads(_req('GET', rname))
            try:
                _req('DELETE', rname)
            except Exception:  # noqa: BLE001
                pass
            return res
        print('  ждём результат...', file=sys.stderr)
    return {'error': f'timeout ждали {timeout}s', 'id': jid}


def submit_many(zadaniya, threads=6, timeout=1800):
    """Пачка заданий разом. Серверный пул — 8 воркеров, так что больше 6-7 одновременно с одной
    сессии ставить не надо: вторая сессия тоже работает, и пул общий.

    zadaniya: список пар (task, args) либо словарей {'task':..., 'args':...}.
    Возвращает список результатов в том же порядке.

    Раньше это было нельзя из-за совпадения id (см. `_now_id`). Теперь можно, но тяжёлые
    задания всё равно идут через свой пул на 1 воркер — пачка из шести `enrich_contacts`
    **без** `site_crawl` выстроится в очередь и часть упрётся в таймаут. Для краулов
    контактов обязательно `"site_crawl": true`.
    """
    norm = []
    for z in zadaniya:
        norm.append((z['task'], z.get('args') or {}) if isinstance(z, dict) else (z[0], z[1]))
    out = [None] * len(norm)

    def odno(i):
        task, args = norm[i]
        try:
            return i, submit(task, args, timeout=timeout)
        except Exception as e:  # noqa: BLE001
            return i, {'error': f'{type(e).__name__}: {str(e)[:200]}', 'task': task}

    with ThreadPoolExecutor(max_workers=threads) as pool:
        for i, res in pool.map(odno, range(len(norm))):
            out[i] = res
    return out


if __name__ == '__main__':
    # Пачка: run_on_server.py --many '[{"task":"fetch_url","args":{...}}, ...]' [--threads 6]
    if len(sys.argv) >= 3 and sys.argv[1] == '--many':
        thr = int(sys.argv[sys.argv.index('--threads') + 1]) if '--threads' in sys.argv else 6
        res = submit_many(json.loads(sys.argv[2]), threads=thr)
        print(json.dumps(res, ensure_ascii=False, indent=1))
        sys.exit(0)
    if len(sys.argv) < 3:
        print('usage: run_on_server.py <task> <args-json>\n'
              '       run_on_server.py --many \'[{"task":...,"args":{...}},...]\' [--threads 6]',
              file=sys.stderr)
        sys.exit(2)
    out = submit(sys.argv[1], json.loads(sys.argv[2]))
    print(json.dumps(out, ensure_ascii=False, indent=1))
