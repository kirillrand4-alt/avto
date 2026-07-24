#!/usr/bin/env python3
"""Алиасы сотрудников Яндекс 360 через API (в админке пункт из UI пропал).

Зачем: адрес dmarc@ должен существовать (rua= в DMARC-записях доменов), а в
актуальной админке admin.yandex.ru пункта «Редактировать алиасы» нет —
делаем через официальный API 360.

Нужны env:
  Y360_TOKEN   — OAuth-токен админа организации с правами Directory
                 (API Яндекс 360, «Управление сотрудниками: чтение и запись»)
  Y360_ORG_ID  — ID организации (внизу слева в админке, напр. 8534275)

Как получить токен (один раз, под АДМИНСКИМ аккаунтом организации):
  1. oauth.yandex.ru → «Создать приложение» → платформа «Веб-сервисы»,
     Redirect URI: https://oauth.yandex.ru/verification_code
  2. Права: «API Яндекс 360» → Directory: чтение и запись сотрудников.
  3. Открыть https://oauth.yandex.ru/authorize?response_type=token&client_id=<ID приложения>
     под админом → скопировать access_token из адресной строки.
Токен — секрет уровня всей организации: не коммитить, передавать через env,
после работ можно отозвать на oauth.yandex.ru.

Примеры:
  # список сотрудников с алиасами
  python3 sender/tools/y360_aliases.py list
  # добавить алиас dmarc ящику-сборщику
  python3 sender/tools/y360_aliases.py add --user i.lyapin --alias dmarc
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api360.yandex.net/directory/v1"


def _req(method: str, path: str, token: str, body: dict | None = None):
    req = urllib.request.Request(
        API + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"OAuth {token}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        if e.code == 401:
            raise SystemExit("401: токен не принят (протух/не тот аккаунт)")
        if e.code == 403:
            raise SystemExit(
                "403: у токена нет прав Directory write — при создании "
                f"приложения включи «Управление сотрудниками». {detail}")
        raise SystemExit(f"HTTP {e.code}: {detail}")


def _users(org: str, token: str) -> list[dict]:
    users, page = [], 1
    while True:
        data = _req("GET", f"/org/{org}/users?page={page}&perPage=100", token)
        users += data.get("users", [])
        if page >= int(data.get("pages", 1)):
            return users
        page += 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=["list", "add"])
    ap.add_argument("--user", help="nickname или email сотрудника (для add)")
    ap.add_argument("--alias", help="имя алиаса без @домена (для add)")
    args = ap.parse_args()

    token = os.environ.get("Y360_TOKEN", "")
    org = os.environ.get("Y360_ORG_ID", "")
    if not token or not org:
        print("нужны env Y360_TOKEN и Y360_ORG_ID (см. шапку файла)",
              file=sys.stderr)
        return 2

    users = _users(org, token)
    if args.cmd == "list":
        for u in users:
            aliases = ", ".join(u.get("aliases") or []) or "—"
            print(f"{u.get('nickname'):20} {u.get('email', ''):45} "
                  f"алиасы: {aliases}")
        print(f"итого: {len(users)}")
        return 0

    if not args.user or not args.alias:
        print("add: нужны --user и --alias", file=sys.stderr)
        return 2
    want = args.user.lower()
    target = next(
        (u for u in users
         if u.get("nickname", "").lower() == want
         or u.get("email", "").lower() == want
         or u.get("email", "").lower().startswith(want + "@")), None)
    if target is None:
        print(f"сотрудник {args.user!r} не найден (см. list)", file=sys.stderr)
        return 1
    res = _req("POST", f"/org/{org}/users/{target['id']}/aliases", token,
               {"alias": args.alias})
    print(f"ok: {args.alias} → {target.get('email')} "
          f"(алиасы теперь: {', '.join(res.get('aliases') or [])})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
