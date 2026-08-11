# -*- coding: utf-8 -*-
"""Раннер на проверочном VPS: руки сессии + сама проверка адресов.

Зачем отдельная машина. Массовые вопросы «есть ли такой ящик» для антиспама
неотличимы от перебора адресов, а боевой IP один и заменить его дорого: на нём
панель, дроп, сервер отписки. Решение владельца 07.08 — «безопасность в первую
очередь»: проверки унесены сюда. Сгорит этот IP — меняем его, рассылка не
замечает.

Что делает этот процесс:

  1. КАЖДЫЕ 10 МИНУТ сам гоняет проход проверки адресов (probe_worker) —
     отдельная задача в планировщике больше не нужна. Так и задумано: задача,
     про которую никто не знает, жива ли она, — это не автоматизация. Здесь
     один процесс, и его состояние видно по отметкам на дропе;
  2. ПОЛЛИТ ДРОП на задания сессии (файлы vjob-*.json) и исполняет их,
     складывая ответ в vresult-<id>.json.

Почему префикс vjob-, а не job-. На дропе уже живёт раннер боевого сервера, он
разбирает job-*.json. Общий префикс означал бы, что две машины растаскивают
задания друг друга — кто первый успел. Разные префиксы разводят их насовсем.

Безопасность. Задание принимается, только если сходится HMAC-подпись
(JOB_SECRET) — держателю одного DROP_TOKEN подсунуть работу не удастся. Права
намеренно широкие (владелец 07.08: «полные права себе сделай там и рули»):
задача `py` исполняет присланный скрипт, `shell` — команду PowerShell. Machина
одноразовая по назначению: на ней нет ни базы, ни почтовых ящиков, ни ключей
рассылки — только проверка адресов.

Переменные (файл runner-secrets.env рядом со скриптом либо окружение):
DROP_URL, DROP_TOKEN, JOB_SECRET, PROBE_HELO, PROBE_MAIL_FROM.
"""
import argparse
import hashlib
import hmac
import io
import json
import os
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
from datetime import datetime, timezone

КОР = os.path.dirname(os.path.abspath(__file__))
ОПЫ = os.path.join(КОР, "_ops")
ВИДЕЛИ = os.path.join(КОР, ".vps-runner-seen.json")
ЖИВ = "vps-runner-zhiv.json"          # отметка на дропе: процесс дышит
ПРЕФИКС = "vjob-"
ОТВЕТ = "vresult-"
# Порт-замок единственного экземпляра. Занят — значит раннер уже работает.
ЗАМОК_ПОРТ = 47615


def занять_замок():
    """Захватить порт-замок. None — раннер уже работает, второму делать нечего.

    Нужен сторожу. Задача VpsRunner стояла на ОДНОМ триггере — старт системы, —
    и когда процесс умер (11.08 он молчал 18 часов при живой машине), поднять
    его было нечем: следующий старт системы неизвестно когда. Сторож раз в пять
    минут пробует запустить раннер; если тот жив, второй экземпляр упирается в
    занятый порт и тихо выходит. Порт, а не файл: замок снимается сам при любой
    смерти процесса, включая убийство без единого шанса прибрать за собой.
    """
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", ЗАМОК_ПОРТ))
        s.listen(1)
    except OSError:
        s.close()
        return None
    return s


def _env_файл():
    """Подхватить runner-secrets.env рядом со скриптом (как на боевом сервере)."""
    п = os.path.join(КОР, "runner-secrets.env")
    if not os.path.exists(п):
        return
    for с in io.open(п, encoding="utf-8-sig"):
        с = с.strip()
        if not с or с.startswith("#") or "=" not in с:
            continue
        k, v = с.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and v and not v.startswith("<") and k not in os.environ:
            os.environ[k] = v


_env_файл()

DROP_URL = os.environ.get("DROP_URL", "").rstrip("/")
DROP_TOKEN = os.environ.get("DROP_TOKEN", "")
JOB_SECRET = os.environ.get("JOB_SECRET", "")


def лог(м):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {м}", flush=True)


# ---- дроп ---------------------------------------------------------------- #

def _зов(метод, путь, данные=None, таймаут=90):
    з = urllib.request.Request(f"{DROP_URL}/{путь}", data=данные, method=метод,
                               headers={"X-Drop-Token": DROP_TOKEN})
    with urllib.request.urlopen(з, timeout=таймаут) as о:
        return о.read()


def список():
    try:
        д = json.loads(_зов("GET", "list"))
    except Exception as e:  # noqa: BLE001
        лог(f"list не удался: {str(e)[:120]}")
        return []
    файлы = д if isinstance(д, list) else (д.get("files") or [])
    имена = []
    for f in файлы:
        имя = f.get("name") if isinstance(f, dict) else str(f)
        if имя:
            имена.append(имя)
    return имена


def скачать(имя):
    return _зов("GET", имя)


def положить(имя, данные):
    _зов("PUT", имя, данные=данные)


def удалить(имя):
    try:
        _зов("DELETE", имя)
    except Exception as e:  # noqa: BLE001
        лог(f"удалить {имя}: {str(e)[:100]}")


# ---- подпись ------------------------------------------------------------- #

def канон(задание):
    return json.dumps({"id": задание.get("id"), "task": задание.get("task"),
                       "args": задание.get("args", {}), "ts": задание.get("ts")},
                      sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def подпись_верна(задание):
    if not JOB_SECRET:
        return True                    # секрета нет — проверять нечем
    надо = hmac.new(JOB_SECRET.encode("utf-8"), канон(задание).encode("utf-8"),
                    hashlib.sha256).hexdigest()
    return hmac.compare_digest(надо, str(задание.get("sig") or ""))


# ---- задачи -------------------------------------------------------------- #

def задача_ping(args):
    return {"pong": True, "echo": args, "хост": os.environ.get("COMPUTERNAME"),
            "время": datetime.now(timezone.utc).isoformat()}


def задача_py(args):
    """Скачать скрипт с дропа и выполнить его здесь.

    Скрипт приезжает файлом, а не строкой в задании: так его видно на дропе и
    можно перечитать глазами, если что-то пошло не так.
    """
    имя = str(args.get("file") or "")
    if not имя:
        return {"error": "не сказано, какой файл выполнять (file)"}
    os.makedirs(ОПЫ, exist_ok=True)
    тело = скачать(имя)
    путь = os.path.join(ОПЫ, os.path.basename(имя))
    with open(путь, "wb") as f:
        f.write(тело)
        f.flush()
        os.fsync(f.fileno())
    argv = [str(a) for a in (args.get("argv") or [])]
    # Без PYTHONIOENCODING дочерний питон пишет в трубу в кодировке системы
    # (на русской Windows — cp1251), а мы читаем как UTF-8: русский вывод
    # приезжает кашей. Договариваемся об одной кодировке явно.
    среда = dict(os.environ, PYTHONIOENCODING="utf-8")
    p = subprocess.run([sys.executable, путь] + argv, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", env=среда,
                       timeout=int(args.get("timeout") or 1500))
    return {"rc": p.returncode, "файл": путь, "байт": len(тело),
            "stdout_tail": (p.stdout or "")[-6000:],
            "stderr_tail": (p.stderr or "")[-3000:]}


def задача_shell(args):
    """Команда PowerShell. Права широкие — по прямому указанию владельца."""
    команда = str(args.get("cmd") or "")
    if not команда:
        return {"error": "пустая команда"}
    # PowerShell по умолчанию пишет в консольной кодировке (cp866), а мы читаем
    # как UTF-8 — русский вывод приезжает кашей («‘®бв®п­ЁҐ» вместо
    # «Состояние»). Просим его сразу говорить на UTF-8.
    приставка = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
    p = subprocess.run(["powershell", "-NoProfile", "-Command",
                        приставка + команда],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace",
                       timeout=int(args.get("timeout") or 600))
    return {"rc": p.returncode, "stdout_tail": (p.stdout or "")[-6000:],
            "stderr_tail": (p.stderr or "")[-3000:]}


def задача_probe(args):
    """Проход проверки адресов прямо сейчас, не дожидаясь своего часа."""
    return _проход_проверки(лимит=int(args.get("limit") or 60),
                            пауза=float(args.get("pause") or 3.0))


ЗАДАЧИ = {"ping": задача_ping, "py": задача_py, "shell": задача_shell,
          "probe": задача_probe}


# ---- проверка адресов ---------------------------------------------------- #

def _проход_проверки(лимит=60, пауза=3.0):
    """Тот же проход, что делал probe_worker по расписанию."""
    try:
        sys.path.insert(0, КОР)
        import probe_worker  # noqa: PLC0415 - модуль лежит рядом
        сделано = probe_worker.проход(пауза, 3, лимит)
        return {"проверено": сделано}
    except Exception as e:  # noqa: BLE001 - проверка упала, раннер живёт
        лог(f"проход проверки упал: {str(e)[:150]}")
        return {"ошибка": str(e)[:200]}


# ---- главный цикл -------------------------------------------------------- #

def загрузить_виденное():
    try:
        return set(json.load(io.open(ВИДЕЛИ, encoding="utf-8")))
    except Exception:  # noqa: BLE001
        return set()


def сохранить_виденное(видели):
    try:
        with io.open(ВИДЕЛИ, "w", encoding="utf-8") as f:
            json.dump(sorted(видели)[-5000:], f)
    except Exception as e:  # noqa: BLE001
        лог(f"seen не сохранился: {str(e)[:100]}")


def разобрать_задания(видели):
    сделано = 0
    for имя in список():
        if not имя.startswith(ПРЕФИКС) or имя in видели:
            continue
        try:
            задание = json.loads(скачать(имя).decode("utf-8", "replace"))
        except Exception as e:  # noqa: BLE001
            лог(f"{имя}: не читается ({str(e)[:80]})")
            видели.add(имя)
            continue
        ид = str(задание.get("id") or имя)
        задача = str(задание.get("task") or "")
        if not подпись_верна(задание):
            лог(f"{имя}: подпись не сходится — пропускаю")
            видели.add(имя)
            continue
        функция = ЗАДАЧИ.get(задача)
        if функция is None:
            ответ = {"ok": False, "error": f"нет такой задачи: {задача}",
                     "умею": sorted(ЗАДАЧИ)}
        else:
            лог(f"{имя}: {задача}")
            try:
                ответ = {"ok": True, "data": функция(задание.get("args") or {})}
            except Exception as e:  # noqa: BLE001 - задание упало, раннер живёт
                ответ = {"ok": False, "error": str(e)[:300],
                         "trace": traceback.format_exc()[-1500:]}
        ответ["id"] = ид
        ответ["at"] = datetime.now(timezone.utc).isoformat()
        положить(f"{ОТВЕТ}{ид}.json",
                 json.dumps(ответ, ensure_ascii=False).encode("utf-8"))
        удалить(имя)
        видели.add(имя)
        сделано += 1
    return сделано


def отметиться(последняя_проверка):
    """Оставить на дропе отметку «я жив» — иначе о работе машины судить нечем."""
    try:
        положить(ЖИВ, json.dumps({
            "хост": os.environ.get("COMPUTERNAME"),
            "время": datetime.now(timezone.utc).isoformat(),
            "последняя_проверка_адресов": последняя_проверка,
        }, ensure_ascii=False).encode("utf-8"))
    except Exception as e:  # noqa: BLE001
        лог(f"отметка не легла: {str(e)[:100]}")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--poll", type=int, default=20,
                   help="как часто смотреть задания, сек")
    p.add_argument("--probe-every", type=int, default=600,
                   help="как часто гонять проверку адресов, сек (0 — не гонять)")
    p.add_argument("--limit", type=int, default=60,
                   help="сколько адресов за один проход проверки")
    p.add_argument("--once", action="store_true",
                   help="один круг и выход (для проверки установки)")
    p.add_argument("--no-lock", action="store_true",
                   help="не проверять, что раннер уже работает")
    a = p.parse_args()

    замок = None
    if not a.no_lock:
        замок = занять_замок()
        if замок is None:
            print("раннер уже работает — второй экземпляр не нужен")
            return 0

    for ключ in ("DROP_URL", "DROP_TOKEN"):
        if not os.environ.get(ключ):
            print(f"нет переменной {ключ} — раннер не сможет ходить на дроп")
            return 2
    лог(f"раннер запущен: задания каждые {a.poll}с, "
        f"проверка адресов каждые {a.probe_every}с")

    видели = загрузить_виденное()
    последняя = None
    следующая_проверка = 0.0
    последний_вздох = [0.0]
    # Проверка адресов идёт ОТДЕЛЬНОЙ нитью. Раньше она шла прямо в цикле, и
    # раннер на всё её время переставал разбирать задания: 11.08 при лимите 150
    # проход занял около двадцати минут, ping не отвечал, отметка жизни не
    # обновлялась — снаружи это неотличимо от мёртвого раннера. Разница между
    # «занят» и «умер» должна быть видна, иначе сторож и человек чинят не то.
    нить = {"жива": False, "итог": None}

    def _проверка_в_нити(лимит):
        try:
            нить["итог"] = dict(_проход_проверки(лимит=лимит),
                                at=datetime.now(timezone.utc).isoformat())
        except Exception:  # noqa: BLE001 - проход упал, раннер живёт
            нить["итог"] = {"ошибка": traceback.format_exc()[-300:]}
        finally:
            нить["жива"] = False

    while True:
        try:
            n = разобрать_задания(видели)
            if n:
                сохранить_виденное(видели)
        except Exception:  # noqa: BLE001 - круг упал, раннер живёт
            лог("разбор заданий упал:\n" + traceback.format_exc()[-800:])

        if нить["итог"] is not None:
            последняя = нить["итог"]
            нить["итог"] = None
            отметиться(последняя)

        if (a.probe_every and not нить["жива"]
                and time.monotonic() >= следующая_проверка):
            нить["жива"] = True
            следующая_проверка = time.monotonic() + a.probe_every
            threading.Thread(target=_проверка_в_нити, args=(a.limit,),
                             name="probe-pass", daemon=True).start()

        if a.once:
            # Один круг — значит дождаться прохода: иначе проверка установки
            # закончится раньше самой проверки.
            while нить["жива"]:
                time.sleep(2)
            отметиться(нить["итог"] or последняя)
            return 0
        # Отметка жизни раз в минуту, даже пока идёт долгий проход: снаружи
        # должно быть видно, что раннер дышит.
        if time.monotonic() - последний_вздох[0] > 60:
            последний_вздох[0] = time.monotonic()
            отметиться(dict(последняя or {}, zanyat=нить["жива"],
                            dyshit=datetime.now(timezone.utc).isoformat()))
        time.sleep(max(5, a.poll))


if __name__ == "__main__":
    sys.exit(main() or 0)
