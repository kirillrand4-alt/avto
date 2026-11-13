# -*- coding: utf-8 -*-
"""После перезапуска панели: время старта процесса, отправки за 15 мин, scheduled→sending, хвост логов. Только чтение."""
import io, os, sqlite3, subprocess
print(subprocess.run(["powershell", "-NoProfile", "-Command", "$s=Get-CimInstance Win32_Service -Filter \"Name='SenderPanel'\"; Get-CimInstance Win32_Process | ? {$_.ParentProcessId -eq $s.ProcessId} | % { $_.Name + ' ' + $_.CreationDate }; Get-Date"], capture_output=True, text=True, errors="replace").stdout)
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True)
print("последняя отправка:", c.execute("SELECT MAX(sent_at) FROM messages WHERE status='sent'").fetchone(), "| sending:", c.execute("SELECT COUNT(*), MAX(claimed_at) FROM messages WHERE status='sending'").fetchone())
for п in (r"C:\sender\_ops\panel_out.log", r"C:\sender\_ops\panel_err.log"):
    р = os.path.getsize(п)
    with io.open(п, "rb") as f: f.seek(max(0, р - 30000)); х = f.read().decode("utf-8", "replace").splitlines()
    print("==", п); print("\n".join(x[:200] for x in х[-12:] if "GET /api" not in x))
