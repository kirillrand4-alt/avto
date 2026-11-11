# -*- coding: utf-8 -*-
r"""Медленный повтор ЕИС для набора ca (11.11, владелец: п. 5 «применяю»): компании, у которых поиск закупок ЕИС
ответил блоком («999 Forbidden», 403, 434), — заново, 1 поток, запрос не чаще раза в 8 с, на блок — пауза 5–15 мин.
Это kc_zakupki_dobor.py в режиме KC_ZAKUPKI_TOLKO_OSHIBKI=1 (резюм — по журналу; сам останавливается, когда конвейер
ca начинает шаги, пишущие в ca-kontakty.jsonl, — тогда перезапустить после них). Запуск: сам в фон; второй экземпляр
не стартует. Лог — ca\ca_eis_povtor_*.log.
"""
import os, subprocess, sys, time

DIR = r'C:\sender\server'
ПАПКА = os.path.join(DIR, 'ca')
r = subprocess.run(['powershell', '-NoProfile', '-Command',
                    "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like "
                    "'*kc_zakupki_dobor.py*' } | ForEach-Object { $_.ProcessId }"], capture_output=True, text=True, timeout=120)
if r.stdout.split():
    print('===ИТОГ=== уже идёт добор ЕИС, pid', r.stdout.split())
    sys.exit(0)
env = dict(os.environ, KC_NABOR='ca', POISK_NABOR='ca', KC_CEL='kc', KC_ZAKUPKI_TOLKO_OSHIBKI='1',
           KC_ZAKUPKI_POTOKOV='1', KC_EIS_INTERVAL='8', KC_ZAKUPKI_DOBOR_OT='0')
лог = os.path.join(ПАПКА, 'ca_eis_povtor_%s.log' % time.strftime('%d%m-%H%M'))
with open(лог, 'wb') as в:
    p = subprocess.Popen([sys.executable, '-u', os.path.join(DIR, 'kc_zakupki_dobor.py')], cwd=DIR, env=env,
                         creationflags=0x08 | 0x200 | 0x4000, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT,
                         close_fds=False)
time.sleep(90)
print('===ИТОГ=== pid', p.pid, open(лог, encoding='utf-8', errors='replace').read()[-600:])
