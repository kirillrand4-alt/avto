# -*- coding: utf-8 -*-
"""Разведка (только чтение): чем обслуживается 443 и где конфиг Caddy."""
import json
import os
import subprocess

ROOTS = ['C:\\', 'C:\\seostat', 'C:\\sender', 'C:\\caddy', 'C:\\Caddy',
         'C:\\ProgramData', 'C:\\Program Files']
NAMES = ('caddyfile', 'caddyfile.txt', 'caddy.json')


def main():
    out = {}
    try:
        r = subprocess.run(
            ['powershell', '-NoProfile', '-Command',
             "(Get-CimInstance Win32_Service -Filter \"Name='caddy'\").PathName"],
            capture_output=True, text=True, timeout=60)
        out['caddy_служба'] = (r.stdout or r.stderr).strip()[:400]
    except Exception as e:  # noqa: BLE001
        out['caddy_служба'] = str(e)[:150]

    found = []
    for root in ROOTS:
        if not os.path.isdir(root):
            continue
        base_depth = root.rstrip('\\').count(os.sep)
        try:
            for dp, dn, fn in os.walk(root):
                if dp.count(os.sep) - base_depth > 2:
                    dn[:] = []
                    continue
                for f in fn:
                    if f.lower() in NAMES:
                        found.append(os.path.join(dp, f))
        except Exception:  # noqa: BLE001
            pass
        if found:
            break
    out['найденные_конфиги'] = found[:6]
    if found:
        try:
            out['содержимое'] = open(found[0], encoding='utf-8',
                                     errors='replace').read()[:2500]
            out['путь'] = found[0]
        except Exception as e:  # noqa: BLE001
            out['содержимое'] = str(e)[:150]

    # что отвечает локально на 5000 и 8013
    for port in (5000, 8013):
        try:
            import urllib.request
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=6) as r:
                out[f'порт_{port}'] = f'HTTP {r.status}, {r.headers.get("Server", "?")}'
        except Exception as e:  # noqa: BLE001
            out[f'порт_{port}'] = str(e)[:110]

    print(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()
