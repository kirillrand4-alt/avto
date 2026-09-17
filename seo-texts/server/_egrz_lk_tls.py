# -*- coding: utf-8 -*-
"""Почему lk.egrz.ru не открывается: смотрим TLS честно — curl и openssl."""
import json
import subprocess

o = {}


def выполнить(имя, cmd, tmo=60):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=tmo, shell=True)
        o[имя] = {'rc': p.returncode,
                  'out': (p.stdout or '')[-500:],
                  'err': (p.stderr or '')[-500:]}
    except Exception as e:
        o[имя] = 'ОШИБКА: %r' % (e,)


выполнить('curl_lk', 'curl -s -o NUL -w "%{http_code} %{ssl_verify_result}" '
                     '--max-time 40 https://lk.egrz.ru/')
выполнить('curl_lk_openapi', 'curl -s -i --max-time 40 https://lk.egrz.ru/OPENAPI/ | '
                             'findstr /B /C:"HTTP/" /C:"Server" /C:"WWW-Authenticate"')
выполнить('curl_verbose', 'curl -v -s -o NUL --max-time 40 https://lk.egrz.ru/ 2>&1 | '
                          'findstr /C:"SSL" /C:"TLS" /C:"certificate" /C:"alert" /C:"subject"')
выполнить('openssl', 'openssl s_client -connect lk.egrz.ru:443 -servername lk.egrz.ru '
                     '-brief < NUL 2>&1', 60)
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
