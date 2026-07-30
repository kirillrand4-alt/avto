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
import subprocess
import threading
import urllib.request

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


_id_lock = threading.Lock()
_id_seq = [0]


def _now_id():
    """Уникальный id задания — В ТОМ ЧИСЛЕ для потоков одного процесса.

    РАНЬШЕ было `time + pid`, и у всех потоков одного процесса в одну и ту же
    секунду он совпадал. Четыре пачки ложились на дроп ПОД ОДНИМ ИМЕНЕМ и
    затирали друг друга. Симптом обманчив до неузнаваемости: клиент честно
    дожидается результата и отдаёт его — просто это результат ЧУЖОЙ пачки, а
    прогон выглядит успешным. Поймано параллельной сессией 29.07.
    """
    with _id_lock:
        _id_seq[0] += 1
        n = _id_seq[0]
    return f'{int(time.time())}-{os.getpid()}-{threading.get_ident() % 100000}-{n}'


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


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('usage: run_on_server.py <task> <args-json>', file=sys.stderr)
        sys.exit(2)
    out = submit(sys.argv[1], json.loads(sys.argv[2]))
    print(json.dumps(out, ensure_ascii=False, indent=1))
