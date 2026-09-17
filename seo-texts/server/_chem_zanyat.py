# -*- coding: utf-8 -*-
"""Чем занят прогон, если провайдер не нужен: соединения и файлы обогащения."""
import glob, json, os, subprocess, time

DIR = r'C:\sender\server'
o = {'сейчас': time.strftime('%H:%M:%S')}
r = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "$ids=(Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "Where-Object {$_.CommandLine -like '*news_scan*'}).ProcessId; "
     "Get-NetTCPConnection -OwningProcess $ids -State Established -ErrorAction SilentlyContinue | "
     "Select-Object -First 6 RemoteAddress,RemotePort | ConvertTo-Json -Compress"],
    capture_output=True, text=True, timeout=90)
o['соединения'] = (r.stdout or '').strip()[:300]

свежие = []
for п in glob.glob(os.path.join(DIR, '*.jsonl')) + glob.glob(os.path.join(DIR, '*.log')):
    st = os.stat(п)
    if time.time() - st.st_mtime < 3600:
        свежие.append((time.strftime('%H:%M:%S', time.localtime(st.st_mtime)),
                       os.path.basename(п), st.st_size))
o['файлы_за_час'] = sorted(свежие)[-8:]

# Сколько лидов уже обогащено контактами — по стриму обогащения.
for имя in ('enrich_stream_news.jsonl', 'enrich_stream_mass.jsonl'):
    п = os.path.join(DIR, имя)
    if os.path.exists(п):
        st = os.stat(п)
        o.setdefault('обогащение', {})[имя] = {
            'байт': st.st_size,
            'изменён': time.strftime('%H:%M:%S', time.localtime(st.st_mtime))}
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
