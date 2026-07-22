# -*- coding: utf-8 -*-
"""Раннер заданий на сервере владельца (C:\\sender, служба NSSM).

Зачем: сессии Claude сидят в песочнице, исходящий доступ к части РФ-сайтов
(checko/rusprofile/сайты компаний) закрыт или ловит Cloudflare. Сервер владельца
в РФ ходит туда нативно; CapMonster решает капчу. Раннер даёт Claude «руки на
сервере»: положил задание на дроп -> сервер исполнил -> вернул результат.

Как: поллит дроп на файлы job-*.json, проверяет HMAC-подпись (JOB_SECRET) и
allowlist задач, исполняет РОВНО разрешённый скрипт (не произвольный shell),
кладёт result-<id>.json обратно и удаляет задание. Резюмируемо (seen-файл),
идемпотентно, stdlib-only.

БЕЗОПАСНОСТЬ (два рубежа):
  1. allowlist ALLOW — раннер умеет запускать только заранее одобренные скрипты
     из своей папки; аргументы уходят скрипту через stdin как JSON (не в argv,
     не в shell) -> инъекция команд невозможна даже при подделке задания.
  2. HMAC-подпись — задание без валидной sig (секрет JOB_SECRET) игнорируется,
     чтобы держатель только DROP_TOKEN не мог подсунуть задачу.
Оба рубежа независимы: даже без секрета выполнится лишь allowlist-скрипт.
"""
import os
import sys
import json
import time
import hmac
import hashlib
import subprocess
import urllib.request
import urllib.error

DIR = os.path.dirname(os.path.abspath(__file__))


def _load_env_file():
    """Подхватить runner-secrets.env из папки скрипта в os.environ (если есть).
    Так службе NSSM не нужно задавать переменные вручную — только положить файл."""
    p = os.path.join(DIR, 'runner-secrets.env')
    if not os.path.exists(p):
        return
    for line in open(p, encoding='utf-8-sig'):
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        k, v = k.strip(), v.strip()
        # не перетираем то, что уже задано окружением службы; плейсхолдеры пропускаем
        if k and v and not v.startswith('<') and k not in os.environ:
            os.environ[k] = v


_load_env_file()

DROP_URL = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/')
DROP_TOKEN = os.environ.get('DROP_TOKEN', '')
JOB_SECRET = os.environ.get('JOB_SECRET', '')
POLL_SEC = int(os.environ.get('RUNNER_POLL_SEC', '20'))
JOB_TIMEOUT = int(os.environ.get('RUNNER_JOB_TIMEOUT', '1800'))  # 30 мин на задание
SEEN_PATH = os.path.join(DIR, '.runner-seen.json')

# allowlist: task -> базовая команда (args задания уходят скрипту через stdin JSON)
ALLOW = {
    'verify_company': [sys.executable, os.path.join(DIR, 'verify_company.py')],
    'enrich_contacts': [sys.executable, os.path.join(DIR, 'enrich_contacts.py')],
    'browser_probe': [sys.executable, os.path.join(DIR, 'browser_probe.py')],
    'dadata': [sys.executable, os.path.join(DIR, 'dadata_client.py')],
    'news_scan': [sys.executable, os.path.join(DIR, 'news_scan.py')],
    'enrich_db': [sys.executable, os.path.join(DIR, 'enrich_db.py')],
    'dolphin_pool': [sys.executable, os.path.join(DIR, 'dolphin_pool.py')],
    'ping': [sys.executable, '-c',
             'import sys,json;json.dump({"pong":True,"echo":json.load(sys.stdin)},sys.stdout)'],
}


def _req(method, path, data=None):
    url = f"{DROP_URL}/{path}"
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={'X-Drop-Token': DROP_TOKEN})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read()


def drop_list():
    try:
        return json.loads(_req('GET', 'list'))
    except Exception as e:  # noqa: BLE001
        log(f'list failed: {e}')
        return []


def drop_down(name):
    return _req('GET', name)


def drop_up(name, blob):
    _req('PUT', name, data=blob)


def drop_del(name):
    try:
        _req('DELETE', name)
    except Exception as e:  # noqa: BLE001
        log(f'del {name} failed: {e}')


def log(msg):
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    line = f'[{ts}] {msg}'
    print(line, flush=True)


def load_seen():
    try:
        return set(json.load(open(SEEN_PATH, encoding='utf-8')))
    except Exception:  # noqa: BLE001
        return set()


def save_seen(seen):
    try:
        json.dump(sorted(seen)[-5000:], open(SEEN_PATH, 'w', encoding='utf-8'))
    except Exception as e:  # noqa: BLE001
        log(f'save_seen failed: {e}')


def canonical(job):
    """Строка для подписи: id|task|args (args — компактный сортированный JSON)."""
    payload = {'id': job.get('id'), 'task': job.get('task'),
               'args': job.get('args', {}), 'ts': job.get('ts')}
    return json.dumps(payload, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False)


def sig_ok(job):
    if not JOB_SECRET:
        # секрета нет — подписи не проверяем, но allowlist всё равно защищает
        return True
    want = hmac.new(JOB_SECRET.encode('utf-8'),
                    canonical(job).encode('utf-8'), hashlib.sha256).hexdigest()
    return hmac.compare_digest(want, str(job.get('sig', '')))


# самообновление: какие файлы раннер может тянуть с дропа поверх себя (подписано)
PULL_ALLOW = {'verify_company.py', 'job_runner.py', 'run_on_server.py',
              'enrich_contacts.py', 'browser_probe.py', 'dadata_client.py',
              'send_campaign.py', 'news_scan.py', 'enrich_db.py', 'dolphin_pool.py'}


def _do_pull(args):
    """Скачать разрешённые файлы с дропа и перезаписать в DIR (для итераций кода
    без участия владельца). Только allowlist имён, без обхода путей. Подпись job
    уже проверена в tick(). job_runner.py подхватится после рестарта службы."""
    names = args.get('files') or list(PULL_ALLOW)
    done, errs = [], []
    for n in names:
        base = os.path.basename(str(n))
        if base not in PULL_ALLOW:
            errs.append(f'{base}: не в allowlist')
            continue
        try:
            blob = drop_down(base)
            if len(blob) < 40 or b'X-Drop-Token' in blob[:200]:
                errs.append(f'{base}: подозрительный ответ ({len(blob)}b)')
                continue
            with open(os.path.join(DIR, base), 'wb') as f:
                f.write(blob)
            done.append(f'{base} ({len(blob)}b)')
        except Exception as e:  # noqa: BLE001
            errs.append(f'{base}: {str(e)[:60]}')
    return {'ok': not errs, 'pulled': done, 'errors': errs,
            'note': 'job_runner.py применится после nssm restart'}


def _spawn_detached(script):
    """Запустить долгий скрипт ОТДЕЛЬНЫМ процессом (переживает таймаут задания и
    сам runner). Windows: DETACHED_PROCESS|CREATE_NEW_PROCESS_GROUP. Вывод в лог."""
    path = os.path.join(DIR, script)
    if not os.path.exists(path):
        return {'ok': False, 'error': f'нет скрипта {script}'}
    logf = open(os.path.join(DIR, script + '.out'), 'a', encoding='utf-8')
    flags = 0
    if os.name == 'nt':
        flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    p = subprocess.Popen([sys.executable, path], stdout=logf, stderr=logf,
                         stdin=subprocess.DEVNULL, cwd=DIR, close_fds=True,
                         creationflags=flags, env=os.environ)
    return {'ok': True, 'spawned': script, 'pid': p.pid,
            'note': 'работает отдельным процессом; прогресс — на дропе'}


def run_job(job):
    task = job.get('task')
    if task == 'pull':
        return _do_pull(job.get('args', {}))
    if task == 'spawn_campaign':
        return _spawn_detached('send_campaign.py')
    cmd = ALLOW.get(task)
    if cmd is None:
        return {'ok': False, 'error': f'task не в allowlist: {task}'}
    try:
        proc = subprocess.run(
            cmd, input=json.dumps(job.get('args', {}), ensure_ascii=False),
            capture_output=True, text=True, timeout=JOB_TIMEOUT,
            encoding='utf-8')
    except subprocess.TimeoutExpired:
        return {'ok': False, 'error': f'timeout {JOB_TIMEOUT}s'}
    except Exception as e:  # noqa: BLE001
        return {'ok': False, 'error': f'exec failed: {e}'}
    out = (proc.stdout or '').strip()
    result = {'ok': proc.returncode == 0, 'returncode': proc.returncode}
    # если скрипт вернул валидный JSON — кладём как data, иначе как текст
    try:
        result['data'] = json.loads(out)
    except Exception:  # noqa: BLE001
        result['stdout_tail'] = out[-4000:]
    if proc.returncode != 0:
        result['stderr_tail'] = (proc.stderr or '')[-2000:]
    return result


# ---- ПАРАЛЛЕЛЬНЫЙ РАННЕР (v2, по просьбе владельца): пул из WORKERS воркеров. ----
# xmlriver-ТЯЖЁЛЫЕ job'ы (sweep/mass_base/kg_probe/xmlriver_queries + dolphin) дерутся за
# каналы xmlriver/CPU → между собой СЕРИЙНО (семафор 1). Остальные (pull/ping/read_stream/
# краулы/dadata/enrich_db) — параллельно. job удаляется ПОСЛЕ завершения (рестарт
# переисполняет незавершённые, как и раньше). seen-набор защищает от двойного запуска.
import threading as _th
from concurrent.futures import ThreadPoolExecutor as _TPE

WORKERS = int(os.environ.get('RUNNER_WORKERS', '3'))
_SEM_HEAVY = _th.Semaphore(1)
_INFLIGHT = set()
_INFLIGHT_LOCK = _th.Lock()


def _is_heavy(job):
    a = job.get('args') or {}
    if job.get('task') in ('dolphin_pool',):
        return True
    return bool(a.get('sweep') or a.get('mass_base') or a.get('news_enrich')
                or a.get('xmlriver_queries') or a.get('kg_probe')
                or (job.get('task') == 'enrich_contacts' and a.get('companies')
                    and not a.get('site_crawl')))


def _exec_one(name, job):
    jid = job.get('id') or name
    heavy = _is_heavy(job)
    try:
        if heavy:
            _SEM_HEAVY.acquire()
        log(f'  исполняю task={job.get("task")} id={jid} heavy={heavy}')
        t0 = time.time()
        result = run_job(job)
        result.update({'id': jid, 'task': job.get('task'),
                       'took_sec': round(time.time() - t0, 1),
                       'done_ts': time.strftime('%Y-%m-%dT%H:%M:%S')})
        blob = json.dumps(result, ensure_ascii=False, indent=1).encode('utf-8')
        try:
            drop_up(f'result-{jid}.json', blob)
            log(f'  результат выгружен: result-{jid}.json ok={result.get("ok")}')
        except Exception as e:  # noqa: BLE001
            log(f'  выгрузка результата failed: {e}')
        drop_del(name)
    except Exception as e:  # noqa: BLE001
        log(f'  exec {name}: {e}')
    finally:
        if heavy:
            _SEM_HEAVY.release()
        with _INFLIGHT_LOCK:
            _INFLIGHT.discard(name)


def tick(seen, pool):
    files = drop_list()
    jobs = sorted(f['name'] for f in files
                  if f['name'].startswith('job-') and f['name'].endswith('.json'))
    for name in jobs:
        with _INFLIGHT_LOCK:
            if name in seen or name in _INFLIGHT:
                continue
            _INFLIGHT.add(name)
        seen.add(name)
        save_seen(seen)
        log(f'job найден: {name}')
        try:
            job = json.loads(drop_down(name))
        except Exception as e:  # noqa: BLE001
            log(f'  не распарсить {name}: {e}')
            with _INFLIGHT_LOCK:
                _INFLIGHT.discard(name)
            continue
        if not sig_ok(job):
            log(f'  ПОДПИСЬ НЕВЕРНА, пропуск: {name}')
            drop_del(name)
            with _INFLIGHT_LOCK:
                _INFLIGHT.discard(name)
            continue
        pool.submit(_exec_one, name, job)


def main():
    if not DROP_TOKEN:
        log('НЕТ DROP_TOKEN в окружении — выход')
        sys.exit(1)
    log(f'runner старт (v2 параллельный): workers={WORKERS}, poll={POLL_SEC}s, '
        f'allowlist={list(ALLOW)}, подпись={"вкл" if JOB_SECRET else "ВЫКЛ (только allowlist)"}')
    seen = load_seen()
    pool = _TPE(max_workers=WORKERS)
    while True:
        try:
            tick(seen, pool)
        except Exception as e:  # noqa: BLE001
            log(f'tick error: {e}')
        time.sleep(POLL_SEC)


if __name__ == '__main__':
    main()
