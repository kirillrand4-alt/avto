# -*- coding: utf-8 -*-
"""Возвращаю вход в панель обзвона: порт держит РУЧНОЙ процесс без окружения службы.

Что найдено замером (ничего не угадано):
  * POST /centro/login отдаёт 503 «CENTRO_SESSION_SECRET не настроен» — и локально, и через
    сайт; значит войти не может никто, ни владелец, ни продавцы;
  * служба `obzvon` (nssm) настроена ПРАВИЛЬНО: венв-питон C:\\seostat\\.venv и окружение с
    CENTRO_SESSION_SECRET, но сама числится PAUSED;
  * порт 8012 слушает PID 5088 — «C:\\Program Files\\Python311\\python.exe -m uvicorn
    app.obzvon:app», то есть СИСТЕМНЫЙ питон, поднятый вручную и без переменных службы.

Лечение: убрать ручной процесс и поднять службу — она стартует с нужным окружением.

ОТКАТ обязателен: если служба за 20 секунд не поднимется, возвращаю ручной запуск тем же
способом, каким он был, чтобы панель отвечала хотя бы как сейчас. Панель боевая, и уйти из
починки в «вообще не отвечает» нельзя.
"""
import io, json, subprocess, sys, time
import urllib.error, urllib.parse, urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
URL = 'http://127.0.0.1:8012/obzvon/centro/login'
TELO = urllib.parse.urlencode({'username': 'проба', 'password': 'проба'}).encode()


def ps(cmd, t=120):
    r = subprocess.run(['powershell', '-Command', cmd], capture_output=True, text=True, timeout=t)
    return (r.stdout or r.stderr).strip()


def proba():
    """(код GET, код POST) — POST 503 означает «секрета нет», 401/200 значит вход живой."""
    out = []
    for dannye in (None, TELO):
        try:
            req = urllib.request.Request(URL, data=dannye)
            if dannye:
                req.add_header('Content-Type', 'application/x-www-form-urlencoded')
            with urllib.request.urlopen(req, timeout=20) as r:
                out.append(r.status)
        except urllib.error.HTTPError as e:
            out.append(e.code)
        except Exception as e:  # noqa: BLE001
            out.append(str(e)[:60])
    return out


o = {'до': proba()}
pid = ps("(Get-NetTCPConnection -LocalPort 8012 -State Listen -ErrorAction SilentlyContinue)"
         ".OwningProcess").strip().splitlines()
pid = pid[0].strip() if pid else ''
o['pid_do'] = pid
o['komandnaya_stroka_do'] = ps(
    "(Get-CimInstance Win32_Process -Filter \"ProcessId=%s\").CommandLine" % pid)[:200] if pid else ''

if o['до'][1] != 503:
    o['вывод'] = 'вход уже работает, ничего не трогаю'
    print(json.dumps(o, ensure_ascii=False, indent=1))
    raise SystemExit(0)

# 1. снять ручной процесс
if pid:
    o['stop_ruchnogo'] = ps("Stop-Process -Id %s -Force; 'снят'" % pid)[:120]
    time.sleep(2)
# 2. поднять службу (из PAUSED сперва stop, иначе start не сработает)
o['sc_stop'] = ps("sc.exe stop obzvon | Out-String")[:200]
time.sleep(3)
o['sc_start'] = ps("sc.exe start obzvon | Out-String")[:200]
for _ in range(10):
    time.sleep(2)
    p = proba()
    if p[0] == 200:
        break
o['после_sluzhby'] = p
o['sc_state'] = ps("(sc.exe query obzvon | Out-String)")[:200]
o['pid_posle'] = ps("(Get-NetTCPConnection -LocalPort 8012 -State Listen "
                    "-ErrorAction SilentlyContinue).OwningProcess")[:40]

if p[0] != 200:
    # ОТКАТ: возвращаем ручной запуск тем же способом, каким он был
    o['ОТКАТ'] = ps(
        "Start-Process -FilePath 'C:\\Program Files\\Python311\\python.exe' "
        "-ArgumentList '-m','uvicorn','app.obzvon:app','--host','127.0.0.1','--port','8012' "
        "-WorkingDirectory 'C:\\seostat' -WindowStyle Hidden; 'ручной запуск возвращён'")[:200]
    time.sleep(6)
    o['после_отката'] = proba()
print(json.dumps(o, ensure_ascii=False, indent=1))
