#!/usr/bin/env python3
"""Продлить сессию групбая: панель по долгому токену выдаёт новый _gbs_jwt на 30 минут.

Поддомены инструментов (ahrefs.groupbuyseo.org и др.) пускают по cookie _gbs_jwt,
выданной на .groupbuyseo.org, поэтому отдельные cookie каждого инструмента не нужны
(проверено 10.11.2026). Файл cookie - строка из «Copy as cURL» запроса панели
check-session (значение -b); лежит только в скратчпаде, chmod 600.

    GBS_COOKIE_FILE=... python3 gbs_refresh.py      # перезапишет _gbs_jwt в файле
"""
import os
import re
import sys
import urllib.parse

import httpx

SP = os.environ.get('GBS_COOKIE_FILE',
                    '/tmp/claude-0/-home-user-avto/20e1aa6d-1000-514f-959c-428ea037ecc1/scratchpad/gbs_panel.txt')
URL = 'https://admin-api.groupbuyseo.org/api/customer/auth/check-session'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36')


def refresh(path=SP):
    ck = open(path, encoding='utf-8').read().strip()
    m = re.search(r'gbs_auth_token=([^;]+)', ck)
    if not m:
        raise SystemExit('в файле нет gbs_auth_token')
    tok = urllib.parse.unquote(m.group(1))
    r = httpx.get(URL, timeout=60, headers={
        'authorization': f'Bearer {tok}', 'accept': 'application/json',
        'origin': 'https://my.groupbuyseo.org', 'user-agent': UA, 'cookie': ck})
    jwt = r.cookies.get('_gbs_jwt') or (r.json().get('_gbs_jwt') if r.status_code == 200 else None)
    if r.status_code != 200 or not jwt:
        raise SystemExit(f'сессия не продлена: HTTP {r.status_code} {r.text[:120]}')
    ck = re.sub(r'_gbs_jwt=[^;]*', '_gbs_jwt=' + jwt, ck) if '_gbs_jwt=' in ck else ck + '; _gbs_jwt=' + jwt
    fd = os.open(path, os.O_WRONLY | os.O_TRUNC | os.O_CREAT, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(ck)
    return True


if __name__ == '__main__':
    refresh(sys.argv[1] if len(sys.argv) > 1 else SP)
    print('сессия продлена на 30 минут')
