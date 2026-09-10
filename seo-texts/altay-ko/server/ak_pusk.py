# -*- coding: utf-8 -*-
"""Запуск долгих прогонов прямо на сервере, отдельными процессами.
Гонялка из песочницы живёт только пока жива моя сессия, а обход 15 000 ИНН идёт часами -
поэтому процессы отвязываем от родителя (DETACHED_PROCESS) и пишем их вывод в лог рядом с базой.
argv: имя_скрипта бюджет [доп. аргументы] | STOP - погасить ранее запущенные | SPISOK - что живо."""
import os, sys, time, subprocess
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
AK = r'C:\sender\_ops\ak'
PID = os.path.join(AK, 'puski.txt')

def zhivye():
    out = subprocess.run(['powershell', '-NoProfile', '-c',
                          "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | % { \"$($_.ProcessId)`t$($_.CommandLine)\" }"],
                         capture_output=True, text=True, timeout=90).stdout
    return [l for l in out.splitlines() if '_ops\\ak\\' in l]

if 'SPISOK' in sys.argv:
    for l in zhivye(): print('  ', l.strip()[:150])
    sys.exit(0)
if 'STOP' in sys.argv:
    n = 0
    for l in zhivye():
        pid = l.split('\t')[0].strip()
        if pid.isdigit():
            subprocess.run(['taskkill', '/F', '/PID', pid], capture_output=True); n += 1
    print('погашено процессов:', n); sys.exit(0)

skript = sys.argv[1]; byudzhet = sys.argv[2] if len(sys.argv) > 2 else '20000'
dop = sys.argv[3:]
put = os.path.join(AK, skript)
if not os.path.exists(put): print('нет скрипта', put); sys.exit(1)
log = os.path.join(AK, 'log-' + skript.replace('.py', '') + ('-' + '-'.join(dop) if dop else '') + '.txt')
f = open(log, 'a', encoding='utf-8')
f.write(f'\n===== пуск {time.strftime("%Y-%m-%d %H:%M:%S")} бюджет {byudzhet} {" ".join(dop)}\n'); f.flush()
FLAGI = 0x00000008 | 0x00000200   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
p = subprocess.Popen([sys.executable, put, byudzhet] + dop, stdout=f, stderr=subprocess.STDOUT,
                     cwd=AK, creationflags=FLAGI, close_fds=True)
print('запущен', skript, ' '.join(dop), '| pid', p.pid, '| лог', log)
open(PID, 'a', encoding='utf-8').write(f'{time.strftime("%H:%M:%S")}\t{p.pid}\t{skript} {" ".join(dop)}\n')
