# -*- coding: utf-8 -*-
# 11.10 15:40: замена агентов финала meyer7 на ходу. Поиск агентов (xmlriver) упирался в лимит каналов: «поиск не
# ответил» у 41–56 из 60 последних. kc_agent_glubokiy исправлен (очередь на каналы, терпеливые повторы, слепые пустые
# итоги — заново). Оркестратор ждёт агентов по метке процесса (pilot_konveyer.процесс_идёт, опрос раз в минуту), поэтому:
# сначала новые процессы с теми же метками и тем же окружением (Волны.env_шага), потом — гасим только старые PID.
import io, json, os, subprocess, sys, time
DIR = r'C:\sender\server'
os.environ.update({  # как _pusk_meyer7_final_s_obhoda.py (окружение оркестратора финала)
    'POISK_NABOR': 'meyer7', 'KC_NABOR': 'meyer7', 'POISK_REGIONY_SVERKI': 'все', 'PILOT_VOLNY': '1',
    'KC_EC': '1', 'KC_EC_XML_OT': '5e8', 'KC_EC_BEZ_MODELI': '1', 'KC_LIMIT_MIN': '25',
    'KC_POTOKOV': '96', 'KC_MODEL_PARALLEL': '32', 'KC_PROTSESSOV': '6',
    'PILOT_SAYTY_MAX': '24000', 'KC_AGENT_XML_MIN': '60',
    'PILOT_MODEL': 'gpt-6-luna', 'PROVIDER_FALLBACK_CHEAP': 'gpt-5.6-luna'})
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
import pilot_konveyer as PK  # noqa: E402

КАНАЛОВ = {'kc_agent_glubokiy.py': '5', 'kc_agent_glubokiy.py:хвост': '3'}


def pids(метка):
    r = subprocess.run(['powershell', '-NoProfile', '-Command',
                        "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and "
                        "$_.CommandLine -like '*%s' } | ForEach-Object { $_.ProcessId }" % метка],
                       capture_output=True, text=True, timeout=120)
    return [p for p in r.stdout.split() if p.isdigit()]


w = PK.Волны()
o = {}
for ш in КАНАЛОВ:
    старые = pids(PK.метка(ш))
    файл = ш.partition(':')[0]
    cmd = [PK.питон(файл), '-u', os.path.join(DIR, файл)] + PK.метка(ш).split()
    лог = w.лог(ш)
    with open(лог, 'ab') as f:
        p = subprocess.Popen(cmd, cwd=DIR, env=dict(w.env_шага(ш), KC_XML_KANALOV=КАНАЛОВ[ш]), stdout=f,
                             stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, creationflags=0x08 | 0x200, close_fds=False)
    time.sleep(3)
    убиты = []
    for pid in старые:
        if pid != str(p.pid):
            r = subprocess.run(['taskkill', '/PID', pid, '/F'], capture_output=True, text=True)
            убиты.append((pid, r.returncode))
    o[ш] = {'новый': p.pid, 'старые': убиты, 'лог': os.path.basename(лог), 'модель': w.env_шага(ш)['PROVIDER_MODEL']}
time.sleep(60)
for ш in КАНАЛОВ:
    o[ш]['живые'] = pids(PK.метка(ш))
    л = os.path.join(DIR, o[ш]['лог'])
    o[ш]['хвост'] = io.open(л, encoding='utf-8', errors='replace').read()[-300:] if os.path.exists(л) else ''
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
