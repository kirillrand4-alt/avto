# -*- coding: utf-8 -*-
"""Послать команду на проверочный VPS в обход python-раннера.

Нужен, когда раннер мёртв — то есть ровно тогда, когда его надо чинить. До
11.08 такого пути не было: единственной рукой на машине был сам раннер, и
доставить в него исправление можно было только через него же. Три раза подряд
пришлось звать владельца к RDP из-за моих же правок.

Здесь другой конец аварийного канала (второй — vps-bootstrap.ps1, задача
планировщика раз в пять минут):

    я    -> vps-komanda.json     {id, ps, sig}
    VPS  -> vps-otvet-<id>.json  {id, out, at}

Подпись HMAC-SHA256 на JOB_SECRET по строке "<id>\\n<ps>" — та же, что у
раннера: одного DROP_TOKEN недостаточно, чтобы прислать сюда команду.

    python3 vps_komanda.py 'Get-Process python | Format-List'
    python3 vps_komanda.py --file моя.ps1 --wait 600
"""
import argparse
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.request

КОР = os.path.dirname(os.path.abspath(__file__))
КОМАНДА = "vps-komanda.json"


def _секреты():
    """Ключи из окружения, иначе из файла раннера рядом со скриптом."""
    из = {}
    п = os.path.join(КОР, "runner-secrets.env")
    if os.path.exists(п):
        for с in open(п, encoding="utf-8-sig"):
            с = с.strip()
            if с and not с.startswith("#") and "=" in с:
                k, v = с.split("=", 1)
                из[k.strip()] = v.strip().strip('"').strip("'")
    for к in ("DROP_URL", "DROP_TOKEN", "JOB_SECRET"):
        if os.environ.get(к):
            из[к] = os.environ[к]
    return из


def _зов(метод, имя, данные=None, таймаут=90):
    с = _секреты()
    з = urllib.request.Request(f"{c_url(с)}/{имя}", data=данные, method=метод,
                               headers={"X-Drop-Token": с.get("DROP_TOKEN", "")})
    with urllib.request.urlopen(з, timeout=таймаут) as о:
        return о.read()


def c_url(с):
    return (с.get("DROP_URL") or "").rstrip("/")


def послать(скрипт: str) -> str:
    """Положить команду на дроп. Возвращает её id."""
    с = _секреты()
    ид = f"{int(time.time())}-{os.getpid()}"
    подпись = ""
    if с.get("JOB_SECRET"):
        подпись = hmac.new(с["JOB_SECRET"].encode("utf-8"),
                           f"{ид}\n{скрипт}".encode("utf-8"),
                           hashlib.sha256).hexdigest()
    тело = json.dumps({"id": ид, "ps": скрипт, "sig": подпись},
                      ensure_ascii=False).encode("utf-8")
    _зов("PUT", КОМАНДА, данные=тело)
    return ид


def забрать(ид: str, ждать: int = 420, шаг: int = 20):
    """Дождаться ответа. None — не дождались (задача ходит раз в 5 минут)."""
    предел = time.time() + ждать
    while time.time() < предел:
        try:
            return json.loads(_зов("GET", f"vps-otvet-{ид}.json", таймаут=60)
                              .decode("utf-8", "replace"))
        except urllib.error.HTTPError:
            pass
        except Exception:  # noqa: BLE001 - сеть моргнула, ждём дальше
            pass
        time.sleep(шаг)
    return None


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("ps", nargs="?", help="команда PowerShell")
    p.add_argument("--file", help="файл со скриптом вместо строки")
    p.add_argument("--wait", type=int, default=420,
                   help="сколько ждать ответа, сек (задача ходит раз в 5 минут)")
    a = p.parse_args()
    скрипт = open(a.file, encoding="utf-8").read() if a.file else (a.ps or "")
    if not скрипт.strip():
        print("нечего посылать")
        return 2
    ид = послать(скрипт)
    print(f"команда положена: {ид} (ждём до {a.wait}с)")
    ответ = забрать(ид, ждать=a.wait)
    if ответ is None:
        print("ответа нет — задача ещё не сработала либо канал не поднят")
        return 1
    print(ответ.get("out") or "(пусто)")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
