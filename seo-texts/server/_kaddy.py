# -*- coding: utf-8 -*-
r"""Через какой адрес панель видна снаружи: конфиг обратного прокси."""
import json, os, subprocess
d = {}
пути = [r'C:\caddy\Caddyfile', r'C:\Caddy\Caddyfile', r'C:\sender\Caddyfile',
        r'C:\ProgramData\Caddy\Caddyfile', r'C:\tools\caddy\Caddyfile',
        r'C:\seostat\Caddyfile']
for п in пути:
    if os.path.exists(п):
        d['файл'] = п
        d['текст'] = open(п, encoding='utf-8', errors='replace').read()[:2500]
        break
if 'файл' not in d:
    out = subprocess.run(['powershell','-NoProfile','-Command',
      "(Get-CimInstance Win32_Process | Where-Object {$_.Name -like 'caddy*'} | "
      "Select-Object -First 1).CommandLine"], capture_output=True, text=True, timeout=90)
    d['команда_caddy'] = (out.stdout or '').strip()[:400]
    # админ-API кэдди отдаёт действующий конфиг
    try:
        import urllib.request
        d['конфиг_из_admin'] = urllib.request.urlopen(
            'http://127.0.0.1:2019/config/', timeout=15).read().decode(
            'utf-8', 'replace')[:2500]
    except Exception as e:
        d['admin_недоступен'] = str(e)[:120]
print(json.dumps(d, ensure_ascii=False, indent=1)[:3200])
