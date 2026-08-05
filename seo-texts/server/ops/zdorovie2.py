# -*- coding: utf-8 -*-
"""Здоровье панелей — вход настоящей парой из OBZVON_USERS.

Прежняя попытка выводила пароль как sha256(CENTRO_SESSION_SECRET + логин) и
получала 401. Код панели показал, почему: она сверяет ПАРЫ логин:пароль из
`OBZVON_USERS` в .env, а формула вывода относится к другой схеме. Признак
подошёл бы к другому замку.

Пара читается в память этого процесса и НЕ ПЕЧАТАЕТСЯ. В вывод идут код
ответа, заголовок страницы и число строк таблицы.
"""
import base64, io, os, re, subprocess, urllib.error, urllib.request


def пары(служба):
    сыр = b''
    for exe in (r'C:\nssm.exe', r'C:\Windows\System32\nssm.exe', 'nssm'):
        try:
            п = subprocess.run([exe, 'get', служба, 'AppEnvironmentExtra'],
                               capture_output=True, timeout=30)
            сыр = п.stdout or b''
            if сыр:
                break
        except Exception:
            continue
    текст = ''
    for код in ('utf-16-le', 'utf-8', 'cp1251'):
        try:
            текст = сыр.decode(код).replace('\x00', '')
            if 'OBZVON_USERS' in текст or 'ENV_FILE' in текст or текст.strip():
                break
        except Exception:
            continue
    м = re.search(r'OBZVON_USERS=([^\r\n]+)', текст)
    if not м:
        # .env панели
        for п_ in (r'C:\seostat\app\.env', r'C:\seostat\.env', r'C:\seostat\app\env'):
            if os.path.exists(п_):
                т = io.open(п_, encoding='utf-8', errors='replace').read()
                м = re.search(r'OBZVON_USERS\s*=\s*([^\r\n]+)', т)
                if м:
                    break
    if not м:
        return []
    сырьё = м.group(1).strip().strip('"').strip("'")
    из = []
    for кусок in re.split(r'[,;\s]+', сырьё):
        if ':' in кусок:
            л, _, п_ = кусок.partition(':')
            из.append((л.strip(), п_.strip()))
    return из


for порт, служба in ((8012, 'obzvon'), (8014, 'p25obzvon')):
    сп = пары(служба)
    print(f'=== порт {порт} ({служба}): пар логин:пароль найдено {len(сп)}')
    if not сп:
        print('   OBZVON_USERS не прочитан — вход не проверен')
        continue
    ок = False
    for логин, пароль in сп[:3]:
        цепь = base64.b64encode(f'{логин}:{пароль}'.encode()).decode()
        зпр = urllib.request.Request(f'http://127.0.0.1:{порт}/',
                                     headers={'Authorization': 'Basic ' + цепь})
        try:
            о = urllib.request.urlopen(зпр, timeout=25)
            тело = о.read(800000).decode('utf-8', 'replace')
            загл = re.search(r'<title[^>]*>(.{0,90}?)</title>', тело, re.I | re.S)
            print(f'   вход {логин:8} → {о.getcode()} | '
                  f'заголовок={" ".join((загл.group(1) if загл else "").split())[:44]!r} | '
                  f'строк таблицы {len(re.findall(r"<tr[ >]", тело))} | байт {len(тело)}')
            ок = True
            break
        except urllib.error.HTTPError as e:
            print(f'   вход {логин:8} → {e.code} {e.reason}')
        except Exception as e:
            print(f'   вход {логин:8} → СБОЙ {type(e).__name__}: {str(e)[:50]}')
    if not ок:
        print('   ВХОД НЕ ПРОШЁЛ — панель за заслоном не проверена')
