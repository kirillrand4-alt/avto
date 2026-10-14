# -*- coding: utf-8 -*-
"""Остановить процесс по pid (только python partiya_gen/ops): stop_pid.py <pid>"""
import subprocess
import sys
pid = int(sys.argv[1])
кс = subprocess.run(["powershell", "-NoProfile", "-Command",
                     "(Get-CimInstance Win32_Process -Filter 'ProcessId=%d').CommandLine" % pid],
                    capture_output=True, text=True, timeout=60).stdout.strip()
if "partiya_gen.py" not in кс and "server\\ops" not in кс:
    print("не наш процесс, не трогаю: %s" % кс[:120])
else:
    subprocess.run(["powershell", "-NoProfile", "-Command", "Stop-Process -Id %d -Force" % pid], timeout=60)
    print("остановлен %d: %s" % (pid, кс[-120:]))
print("=== STOP PID ===")
