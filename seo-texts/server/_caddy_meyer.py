import subprocess, glob, os, re
print('===ИТОГ===')
r = subprocess.run(['powershell', '-NoProfile', '-Command',
  "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'caddy*' } | Select-Object -ExpandProperty CommandLine"], capture_output=True, text=True, timeout=60)
print('caddy:', r.stdout.strip()[:300])
кандидаты = set(re.findall(r'(?:--config|-c)\s+"?([^"\s]+)', r.stdout))
for корень in (r'C:\caddy', r'C:\Caddy', r'C:\seostat', r'C:\sender', r'C:\tools'):
    кандидаты |= set(glob.glob(корень + r'\Caddyfile*')) | set(glob.glob(корень + r'\**\Caddyfile*', recursive=True)[:5])
for п in кандидаты:
    try: т = open(п, encoding='utf-8', errors='replace').read()
    except Exception: continue
    for м in re.finditer(r'[^\n]*obzvon-meyer[^\n]*(\n[^\n]*){0,6}', т):
        print(п, '::\n', м.group(0)[:500])
r = subprocess.run(['powershell', '-NoProfile', '-Command',
  "Get-NetTCPConnection -State Listen | Where-Object { $_.LocalPort -ge 8000 -and $_.LocalPort -le 8100 } | ForEach-Object { $p = Get-CimInstance Win32_Process -Filter \"ProcessId=$($_.OwningProcess)\"; '{0} {1}' -f $_.LocalPort, $p.CommandLine }"],
  capture_output=True, text=True, timeout=120)
print(r.stdout[-2500:])
