# -*- coding: utf-8 -*-
"""Откуда приложение обзвона берёт CENTRO_SESSION_SECRET и почему его нет.

Вход в панель сейчас отдаёт 503 «CENTRO_SESSION_SECRET не настроен или слишком короткий» —
и локально, и через сайт. Значит войти не может никто: ни владелец, ни продавцы. Прежде чем
трогать боевую службу, СМОТРИМ, где секрет должен лежать и лежит ли он там.

Ничего не меняем: только читаем настройки службы, ищем файлы окружения и проверяем, видит ли
переменную ЖИВОЙ процесс, который слушает 8012. Значение секрета не печатаем — только длину.
"""
import io, json, os, re, subprocess, sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


def ps(cmd, t=90):
    r = subprocess.run(['powershell', '-Command', cmd], capture_output=True, text=True, timeout=t)
    return (r.stdout or r.stderr).strip()


o = {}
# 1. как заведена служба (nssm держит окружение в реестре)
o['reestr_Parameters'] = ps(
    r"Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Services\obzvon\Parameters' "
    r"-ErrorAction SilentlyContinue | Format-List | Out-String")[:1200]
# 2. где nssm на самом деле
o['nssm_put'] = ps("(Get-Command nssm -ErrorAction SilentlyContinue).Source; "
                   "Get-ChildItem C:\\ -Filter nssm.exe -Recurse -Depth 3 "
                   "-ErrorAction SilentlyContinue | Select-Object -First 3 -Expand FullName")[:300]
# 3. файлы окружения рядом с приложением
najd = []
for korn in (r'C:\seostat', r'C:\sender'):
    for root, dirs, files in os.walk(korn):
        if root.count(os.sep) > 4:
            dirs[:] = []
            continue
        for f in files:
            if f.lower() in ('.env', 'env', 'obzvon.env', 'centro.env', '.env.local',
                             'settings.env', 'service.env'):
                najd.append(os.path.join(root, f))
o['fayly_okruzheniya'] = najd[:10]
for f in najd[:10]:
    try:
        t = open(f, encoding='utf-8', errors='replace').read()
        m = re.search(r'CENTRO_SESSION_SECRET\s*=\s*(\S+)', t)
        o['secret_v_' + os.path.basename(f)] = ('есть, длина %d' % len(m.group(1))) if m else 'нет'
    except OSError as e:
        o['secret_v_' + os.path.basename(f)] = 'не прочитан: %s' % e
# 4. видит ли переменную живой процесс на 8012
o['pid_8012'] = ps("(Get-NetTCPConnection -LocalPort 8012 -State Listen "
                   "-ErrorAction SilentlyContinue).OwningProcess")[:40]
o['secret_v_processe'] = ps(
    "$p=(Get-NetTCPConnection -LocalPort 8012 -State Listen -ErrorAction SilentlyContinue)."
    "OwningProcess; if($p){ $e=(Get-CimInstance Win32_Process -Filter \"ProcessId=$p\")."
    "CommandLine; \"командная строка: $e\" }")[:400]
# 5. где приложение читает переменную
for f in (r'C:\seostat\app\routes_centro.py', r'C:\seostat\app\main.py',
          r'C:\seostat\app\__init__.py', r'C:\seostat\app\auth.py'):
    if os.path.exists(f):
        t = open(f, encoding='utf-8', errors='replace').read()
        for m in re.finditer(r'.{0,90}CENTRO_SESSION_SECRET.{0,90}', t):
            o.setdefault('gde_chitaetsya', []).append(
                os.path.basename(f) + ': ' + re.sub(r'\s+', ' ', m.group(0)))
print(json.dumps(o, ensure_ascii=False, indent=1))
