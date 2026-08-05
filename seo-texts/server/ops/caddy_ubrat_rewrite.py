# -*- coding: utf-8 -*-
"""Убрать переписывание /p25 → /obzvon: панель теперь сама живёт на /p25."""
import io, os, re, shutil, subprocess, sys, time
ФАЙЛ = r'C:\Caddyfile'
CADDY = r'C:\caddy.exe'
ПРИМЕНИТЬ = '--apply' in sys.argv
т = io.open(ФАЙЛ, encoding='utf-8', errors='replace').read()
if 'uri replace /p25 /obzvon' not in т:
    print('переписывания в конфиге нет'); raise SystemExit
новый = т.replace('\t\turi replace /p25 /obzvon\n', '')
врем = ФАЙЛ + '.proba'
io.open(врем, 'w', encoding='utf-8').write(новый)
п = subprocess.run([CADDY, 'validate', '--config', врем, '--adapter', 'caddyfile'],
                   capture_output=True, text=True, timeout=90)
print('validate:', 'ПРОШЛА' if п.returncode == 0 else f'ПРОВАЛ {п.returncode}')
if п.returncode:
    os.remove(врем); print((п.stderr or '')[-300:]); raise SystemExit
if not ПРИМЕНИТЬ:
    os.remove(врем); print('СУХОЙ ПРОГОН'); raise SystemExit
бэкап = ФАЙЛ + '.bak-' + time.strftime('%Y%m%d-%H%M%S')
shutil.copy2(ФАЙЛ, бэкап)
shutil.move(врем, ФАЙЛ)
р = subprocess.run([CADDY, 'reload', '--config', ФАЙЛ, '--adapter', 'caddyfile'],
                   capture_output=True, text=True, timeout=120)
print('reload rc =', р.returncode)
if р.returncode:
    shutil.copy2(бэкап, ФАЙЛ)
    subprocess.run([CADDY, 'reload', '--config', ФАЙЛ, '--adapter', 'caddyfile'],
                   capture_output=True, timeout=120)
    print('ОТКАТ')
else:
    print('бэкап:', os.path.basename(бэкап))
