# -*- coding: utf-8 -*-
"""Найти порт живой панели и постучаться: 401 - живая, 500 - сломана.

Порты я в прошлый раз выдернул из sender.yaml по слову «port» и получил
465 и 993 - это SMTP и IMAP, к панели отношения не имеющие. Берём порт
честно: у процесса службы спрашиваем, что он слушает.
"""
import json
import subprocess
import urllib.error
import urllib.request

пс = ("$p = (Get-CimInstance Win32_Service -Filter \"Name='SenderPanel'\")"
      ".ProcessId; "
      "$kids = Get-CimInstance Win32_Process -Filter \"ParentProcessId=$p\" | "
      "Select-Object -ExpandProperty ProcessId; "
      "$all = @($p) + $kids; "
      "Get-NetTCPConnection -State Listen | Where-Object {$all -contains "
      "$_.OwningProcess} | Select-Object LocalAddress,LocalPort,OwningProcess | "
      "ConvertTo-Json -Compress")
из = subprocess.run(["powershell", "-NoProfile", "-Command", пс],
                    capture_output=True, text=True, timeout=90)
print("слушает:", (из.stdout or из.stderr).strip()[:400])
порты = []
try:
    д = json.loads(из.stdout.strip() or "[]")
    if isinstance(д, dict):
        д = [д]
    порты = sorted({int(x["LocalPort"]) for x in д})
except Exception as ex:                                            # noqa: BLE001
    print("разбор не вышел:", str(ex)[:80])
print("порты панели:", порты)

for порт in порты or [8000]:
    for путь in ("/api/analytics/dashboard", "/api/health", "/"):
        try:
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{порт}{путь}", timeout=8) as о:
                т = о.read(300).decode("utf-8", "replace")
                print(f"  {порт}{путь}: {о.status} {т[:160]!r}")
        except urllib.error.HTTPError as ex:
            тело = ex.read(200).decode("utf-8", "replace")
            print(f"  {порт}{путь}: HTTP {ex.code} {тело[:120]!r}")
        except Exception as ex:                                    # noqa: BLE001
            print(f"  {порт}{путь}: {type(ex).__name__} {str(ex)[:60]}")
