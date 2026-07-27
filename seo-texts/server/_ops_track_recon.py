# -*- coding: utf-8 -*-
"""Разведка перед поднятием эндпоинта пикселя (только чтение)."""
import json
import os
import socket
import subprocess

CANDIDATE_PORTS = [8014, 8015, 8082, 8083]


def main():
    out = {}
    try:
        r = subprocess.run(['sc', 'query', 'state=', 'all'],
                           capture_output=True, text=True, timeout=60)
        names = [l.split(':', 1)[1].strip() for l in r.stdout.splitlines()
                 if l.strip().startswith('SERVICE_NAME')]
        out['службы_по_теме'] = [n for n in names if any(
            k in n.lower() for k in ('sender', 'unsub', 'panel', 'caddy', 'track'))]
    except Exception as e:  # noqa: BLE001
        out['службы_по_теме'] = str(e)[:150]

    free = []
    for p in CANDIDATE_PORTS:
        s = socket.socket()
        s.settimeout(1.5)
        try:
            s.connect(('127.0.0.1', p))
            free.append({'порт': p, 'свободен': False})
        except Exception:  # noqa: BLE001
            free.append({'порт': p, 'свободен': True})
        finally:
            s.close()
    out['порты'] = free

    out['nssm'] = os.path.exists('C:\\nssm.exe')
    out['caddyfile'] = os.path.exists('C:\\Caddyfile')
    # где лежит пакет sender и точка входа сервера отписки
    for p in ('C:\\sender\\sender\\unsub_server.py', 'C:\\sender\\sender.yaml',
              'C:\\sender\\panel.env'):
        out[p] = os.path.exists(p)
    # каким питоном запущена панель
    try:
        r = subprocess.run(
            ['powershell', '-NoProfile', '-Command',
             "(Get-CimInstance Win32_Service -Filter \"Name='SenderPanel'\").PathName"],
            capture_output=True, text=True, timeout=40)
        out['панель_команда'] = (r.stdout or r.stderr).strip()[:300]
    except Exception as e:  # noqa: BLE001
        out['панель_команда'] = str(e)[:150]
    print(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()
