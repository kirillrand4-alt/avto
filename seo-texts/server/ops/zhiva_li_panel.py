# -*- coding: utf-8 -*-
"""Панель после рестарта: жива ли служба и подхватила ли новый код.

Проверяем не «файл лежит», а «служба им пользуется»: состояние службы,
время старта процесса против времени правки файлов, и живой HTTP-ответ.
"""
import io
import os
import subprocess
import time
import urllib.request

print("=== служба ===")
try:
    из = subprocess.run(["sc", "query", "SenderPanel"], capture_output=True,
                        text=True, timeout=30)
    for строка in из.stdout.splitlines():
        if строка.strip():
            print("  " + строка.strip())
except Exception as ex:                                            # noqa: BLE001
    print(f"  sc query не сработал: {str(ex)[:80]}")

print("\n=== файлы против старта процесса ===")
файлы = ["otkaz_spam.py", "sender.py", "analytics.py", "gates.py",
         "dsn.py", "napravlenie_pisma.py", "confirm.py"]
for ф in файлы:
    п = os.path.join(r"C:\sender\sender", ф)
    if os.path.exists(п):
        print(f"  {ф:<24} изменён {time.strftime('%Y-%m-%d %H:%M', time.gmtime(os.path.getmtime(п)))} UTC")
    else:
        print(f"  {ф:<24} НЕТ")

# когда стартовал процесс службы
try:
    из = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "(Get-Process -Name python* | Sort-Object StartTime -Descending | "
         "Select-Object -First 3 Id,StartTime,Path | Format-Table -AutoSize | Out-String)"],
        capture_output=True, text=True, timeout=60)
    print("\n=== процессы python ===")
    print(из.stdout.strip()[:800] or из.stderr.strip()[:300])
except Exception as ex:                                            # noqa: BLE001
    print(f"процессы не прочитаны: {str(ex)[:80]}")

print("\n=== HTTP ===")
порты = []
try:
    т = io.open(r"C:\sender\sender.yaml", encoding="utf-8").read()
    for строка in т.splitlines():
        if "port" in строка.lower() and ":" in строка:
            цифры = "".join(c for c in строка.split(":")[-1] if c.isdigit())
            if цифры:
                порты.append(int(цифры))
except Exception:                                                  # noqa: BLE001
    pass
for порт in dict.fromkeys(порты + [8000, 8080, 80]):
    for путь in ("/api/health", "/health", "/"):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{порт}{путь}",
                                        timeout=6) as о:
                тело = о.read(200).decode("utf-8", "replace")
                print(f"  {порт}{путь}: {о.status} {тело[:120]!r}")
                break
        except Exception as ex:                                    # noqa: BLE001
            print(f"  {порт}{путь}: {type(ex).__name__} {str(ex)[:60]}")
