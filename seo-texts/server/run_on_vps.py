# -*- coding: utf-8 -*-
"""Клиент раннера проверочного VPS (сторона песочницы).

Пара к server/vps_runner.py. Отличие от run_on_server.py ровно одно и оно
важное: префикс заданий vjob-, а не job-. На дропе живут ДВА раннера — боевого
сервера и проверочной машины. Общий префикс означал бы, что они растаскивают
задания друг друга, кто первый успел; разные префиксы разводят их насовсем.

    python run_on_vps.py ping '{"hi":1}'
    python run_on_vps.py probe '{"limit":40}'
    python run_on_vps.py shell '{"cmd":"Get-Service | Select -First 5"}'

Для «выполни вот этот скрипт» есть отдельная обёртка — runvps.py: она заливает
файл на дроп и вызывает задачу py.
"""
import hashlib
import hmac
import itertools
import json
import os
import sys
import threading
import time
import urllib.request

DROP_URL = os.environ.get("DROP_URL", "https://parsercompressor.online/drop").rstrip("/")
DROP_TOKEN = os.environ.get("DROP_TOKEN", "")
JOB_SECRET = os.environ.get("JOB_SECRET", "")
ПРЕФИКС = "vjob-"
ОТВЕТ = "vresult-"


def _req(метод, путь, данные=None):
    з = urllib.request.Request(f"{DROP_URL}/{путь}", data=данные, method=метод,
                               headers={"X-Drop-Token": DROP_TOKEN})
    with urllib.request.urlopen(з, timeout=90) as о:
        return о.read()


def _секрет_с_дропа():
    global JOB_SECRET
    if JOB_SECRET:
        return
    try:
        blob = _req("GET", "runner-secrets.env").decode("utf-8", "replace")
        for с in blob.splitlines():
            if с.strip().startswith("JOB_SECRET="):
                JOB_SECRET = с.split("=", 1)[1].strip()
    except Exception:  # noqa: BLE001
        pass


_СЧЁТ = itertools.count(1)
_ЗАМОК = threading.Lock()


def _ид():
    """Уникальное имя задания.

    Секунда + PID совпадали у двух заданий одного процесса, и второе молча
    затирало первое на дропе (поймано на боевом раннере). Поэтому в имени есть
    и счётчик, и случайный хвост.
    """
    with _ЗАМОК:
        n = next(_СЧЁТ)
    return (f"{int(time.time())}-{os.getpid()}-{threading.get_ident() % 100000}-"
            f"{n}-{os.urandom(3).hex()}")


def submit(task, args, wait=True, poll=10, timeout=1800):
    _секрет_с_дропа()
    jid = _ид()
    job = {"id": jid, "task": task, "args": args, "ts": int(time.time())}
    канон = json.dumps({"id": job["id"], "task": job["task"],
                        "args": job["args"], "ts": job["ts"]},
                       sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if JOB_SECRET:
        job["sig"] = hmac.new(JOB_SECRET.encode(), канон.encode(),
                              hashlib.sha256).hexdigest()
    _req("PUT", f"{ПРЕФИКС}{jid}.json",
         data=json.dumps(job, ensure_ascii=False).encode("utf-8"))
    print(f"задание на VPS: {ПРЕФИКС}{jid}.json (task={task}, "
          f"подпись={'да' if JOB_SECRET else 'нет'})", file=sys.stderr)
    if not wait:
        return {"submitted": jid}
    край = time.time() + timeout
    имя = f"{ОТВЕТ}{jid}.json"
    while time.time() < край:
        time.sleep(poll)
        try:
            д = json.loads(_req("GET", "list"))
        except Exception:  # noqa: BLE001
            continue
        файлы = д if isinstance(д, list) else (д.get("files") or [])
        if any((f.get("name") if isinstance(f, dict) else f) == имя for f in файлы):
            рез = json.loads(_req("GET", имя))
            try:
                _req("DELETE", имя)
            except Exception:  # noqa: BLE001
                pass
            return рез
        print("  ждём VPS...", file=sys.stderr)
    return {"error": f"timeout ждали {timeout}s", "id": jid}


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: run_on_vps.py <task> <args-json>\n"
              "задачи: ping | probe | py | shell", file=sys.stderr)
        sys.exit(2)
    print(json.dumps(submit(sys.argv[1], json.loads(sys.argv[2])),
                     ensure_ascii=False, indent=1))
