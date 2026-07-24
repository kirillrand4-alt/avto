#!/usr/bin/env python3
"""Построение индекса базы обзвона по ИНН (company_card.build_obzvon_index).

CSV (663 МБ, 161 761 юрлицо) НЕ сохраняется на диск: стримится с дропа
курлом прямо в парсер, на диск ложится только компактный SQLite (~десятки МБ).
Атомарно: пишем во временный файл, по успеху переименовываем. Упал на середине —
просто перезапустить.

Запуск:
  python3 sender/tools/build_obzvon_index.py --out /path/obzvon-index.db
  python3 sender/tools/build_obzvon_index.py --out db.sqlite --csv local.csv
Имя файла на дропе: --drop-name (по умолчанию obzvon_all_2026-07-16.csv).
Нужны env DROP_URL и DROP_TOKEN (как у drop_client.sh).
"""

import argparse
import io
import json
import os
import subprocess
import sys

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sender.company_card import build_obzvon_index  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True, help="путь итогового SQLite-индекса")
    ap.add_argument("--csv", help="локальный CSV (иначе — стрим с дропа)")
    ap.add_argument("--drop-name", default="obzvon_all_2026-07-16.csv")
    args = ap.parse_args()

    tmp = args.out + ".tmp"
    if os.path.exists(tmp):
        os.unlink(tmp)

    proc = None
    if args.csv:
        fh = open(args.csv, encoding="utf-8-sig", newline="")
    else:
        url, token = os.environ.get("DROP_URL"), os.environ.get("DROP_TOKEN")
        if not url or not token:
            print("нужны env DROP_URL и DROP_TOKEN", file=sys.stderr)
            return 2
        proc = subprocess.Popen(
            ["curl", "-sS", "--fail", "-H", f"X-Drop-Token: {token}",
             f"{url}/{args.drop_name}"], stdout=subprocess.PIPE)
        fh = io.TextIOWrapper(proc.stdout, encoding="utf-8-sig", newline="")

    try:
        stats = build_obzvon_index(fh, tmp)
    finally:
        fh.close()
        if proc is not None:
            proc.wait()
    if proc is not None and proc.returncode != 0:
        print(f"curl упал (код {proc.returncode}) — индекс не сохранён",
              file=sys.stderr)
        os.path.exists(tmp) and os.unlink(tmp)
        return 1

    os.replace(tmp, args.out)
    size_mb = os.path.getsize(args.out) / 1e6
    print(json.dumps({"stats": stats, "size_mb": round(size_mb, 1),
                      "out": args.out}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
