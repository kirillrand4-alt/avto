# -*- coding: utf-8 -*-
import io, os, re, subprocess
for п, строк in ((r"C:\seostat\Parser2\metalparser\cli.py", 60),
                 (r"C:\seostat\Parser2\scripts\daily_collect.py", 34)):
    стр = io.open(п, encoding="utf-8", errors="ignore").read().split("\n")
    print("=" * 72)
    print("### %s" % п)
    for i in range(min(строк, len(стр))):
        print("%4d| %s" % (i + 1, стр[i][:110]))
print("=" * 72)
т = io.open(r"C:\seostat\Parser2\webapp\app.py", encoding="utf-8",
            errors="ignore").read()
print("### webapp/app.py — маршруты")
for м in re.finditer(r"@app\.(get|post)\(\s*['\"]([^'\"]+)", т):
    print("   %-6s %s" % (м.group(1).upper(), м.group(2)))
print("\n### запущенные uvicorn/serve")
r = subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
                    "Select-Object @{n='c';e={$_.CommandLine}} | "
                    "Where-Object { $_.c -like '*uvicorn*' -or $_.c -like '*serve*' } | "
                    "Format-List | Out-String"],
                   capture_output=True, text=True, timeout=90)
print((r.stdout or r.stderr)[:900])
