# -*- coding: utf-8 -*-
"""Улики по сетевому пути: proxy-env раннера/системы, как urllib резолвит прокси,
прямой vs через-прокси тест до дропа и dadata, socks/Dolphin."""
import json, os, socket, subprocess, urllib.request
out = {}
# 1) proxy-переменные окружения (раннер наследует env службы)
out['env_proxy'] = {k: os.environ.get(k) for k in
    ('HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy','ALL_PROXY','all_proxy','NO_PROXY','no_proxy')}
# 2) что urllib считает прокси (getproxies — из реестра Windows тоже!)
out['urllib_getproxies'] = urllib.request.getproxies()
# 3) системный прокси из реестра Windows (WinINET)
try:
    r = subprocess.run(['reg','query',
        r'HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings',
        '/v','ProxyServer'], capture_output=True, text=True, timeout=20)
    out['winreg_proxy'] = (r.stdout or r.stderr).strip()[-300:]
    r2 = subprocess.run(['reg','query',
        r'HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings',
        '/v','ProxyEnable'], capture_output=True, text=True, timeout=20)
    out['winreg_proxy_enable'] = (r2.stdout or '').strip()[-150:]
except Exception as e: out['winreg_err'] = str(e)[:100]
# 4) прямой тест: дроп локально (обход прокси) vs через getproxies
def probe(url, use_proxy):
    try:
        if use_proxy:
            op = urllib.request.build_opener()  # с системным прокси
        else:
            op = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # БЕЗ прокси
        req = urllib.request.Request(url, headers={'User-Agent':'diag'})
        with op.open(req, timeout=15) as r:
            return f'{r.status} ({len(r.read(50000))}b)'
    except Exception as e:
        return f'ERR {type(e).__name__}: {str(e)[:80]}'
out['drop_local_noproxy'] = probe('http://127.0.0.1:8787/list', False)
out['dadata_direct_noproxy'] = probe('https://suggestions.dadata.ru/', False)
out['dadata_via_proxy'] = probe('https://suggestions.dadata.ru/', True)
out['checko_direct_noproxy'] = probe('https://checko.ru/', False)
# 5) сколько сокет-соединений висит (утечка дескрипторов?)
try:
    r = subprocess.run(['powershell','-NoProfile','-Command',
        "(Get-NetTCPConnection -ErrorAction SilentlyContinue | Measure-Object).Count"],
        capture_output=True, text=True, timeout=30)
    out['tcp_connections_total'] = (r.stdout or '').strip()
except Exception: pass
print(json.dumps(out, ensure_ascii=False))
