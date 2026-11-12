# -*- coding: utf-8 -*-
"""Здоровье панели: служба SenderPanel, ответ HTTP, нагрузка процесса, свежие ошибки в AppStderr/AppStdout,
отправка за последний час. Только чтение (окружение службы НЕ читаем)."""
import io, os, subprocess, time, urllib.request, sqlite3
ps = lambda к: subprocess.run(["powershell", "-NoProfile", "-Command", к], capture_output=True, text=True, errors="replace", timeout=90).stdout.strip()
print("время сервера:", time.strftime("%Y-%m-%d %H:%M:%S"))
print("служба:", ps("Get-Service SenderPanel | Select Status,StartType | Format-List | Out-String").replace("\n", " "))
print("процесс:", ps("$s=Get-CimInstance Win32_Service -Filter \"Name='SenderPanel'\"; Get-CimInstance Win32_Process | Where {$_.ParentProcessId -eq $s.ProcessId -or $_.ProcessId -eq $s.ProcessId} | "
                     "ForEach { '{0} {1} {2}MB старт {3}' -f $_.ProcessId,$_.Name,[int]($_.WorkingSetSize/1MB),$_.CreationDate }"))
for урл in ("http://127.0.0.1:8012/", "http://127.0.0.1:8012/obzvon/kc"):
    т = time.time()
    try:
        r = urllib.request.urlopen(урл, timeout=30); print("HTTP", урл, r.status, "%.1fс" % (time.time() - т))
    except Exception as ex: print("HTTP", урл, "ОШИБКА", repr(ex)[:150], "%.1fс" % (time.time() - т))
print("CPU:", ps("Get-CimInstance Win32_Processor | Select -Expand LoadPercentage"), "% | свободно RAM:",
      ps("[int]((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1024)"), "MB | диск C свободно:",
      ps("[int]((Get-PSDrive C).Free/1GB)"), "GB")
for путь in (r"C:\sender\_ops\panel_err.log", r"C:\sender\_ops\panel_out.log"):
    if not os.path.exists(путь): print(путь, "нет файла"); continue
    р = os.path.getsize(путь)
    print("\n=== %s изменён %s, %d КБ" % (путь, time.strftime("%H:%M:%S", time.localtime(os.path.getmtime(путь))), р // 1024))
    with io.open(путь, "rb") as f:
        f.seek(max(0, р - 200000)); с = f.read().decode("utf-8", "replace").splitlines()
    плохие = [x for x in с if any(k in x for k in ("Traceback", "ERROR", "Error", "Exception", "locked", "CRITICAL"))]
    print("ошибок в хвосте:", len(плохие)); print("\n".join(x[:220] for x in плохие[-12:]))
    print("--- последние строки:"); print("\n".join(x[:220] for x in с[-8:]))
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True, timeout=30)
print("\nотправлено за 60 мин:", c.execute("SELECT COUNT(*) FROM messages WHERE status='sent' AND sent_at>=datetime('now','-60 minutes')").fetchone()[0],
      "| последняя отправка:", c.execute("SELECT MAX(sent_at) FROM messages WHERE status='sent'").fetchone()[0],
      "| failed за 60 мин:", c.execute("SELECT COUNT(*) FROM messages WHERE status='failed' AND updated_at>=datetime('now','-60 minutes')").fetchone()[0])
