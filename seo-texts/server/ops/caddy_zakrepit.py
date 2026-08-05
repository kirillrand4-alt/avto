# -*- coding: utf-8 -*-
"""Закрепить маршрут /p25 в C:\\Caddyfile, чтобы он пережил перезапуск Caddy.

Правку я внёс через админ-API — она живёт в памяти процесса. При перезапуске
Caddy читает `C:\\Caddyfile`, и панель P25 снова станет недоступной, а владелец
уже на неё рассчитывает. Дописываю блок в файл.

ПРОВЕРКА ДО НЕОБРАТИМОГО: новый конфиг сперва проверяется `caddy validate` во
временном файле. Не прошёл — НЕ ставлю и выхожу. Прежний файл сохраняю рядом.

Запуск: python caddy_zakrepit.py [--apply]
"""
import io, os, re, shutil, subprocess, sys, time

ФАЙЛ = r'C:\Caddyfile'
CADDY = r'C:\caddy.exe'
ПРИМЕНИТЬ = '--apply' in sys.argv
# Конфиг написан именованными матчерами (@obzvon path ...), а не handle /путь*.
# Первый шаблон искал вторую форму и не нашёл места вставки.
БЛОК = """	@p25 path /p25 /p25/*
	handle @p25 {
		uri replace /p25 /obzvon
		reverse_proxy 127.0.0.1:8014
	}

"""

т = io.open(ФАЙЛ, encoding='utf-8', errors='replace').read()
if '/p25' in т:
    print('блок /p25 уже в Caddyfile'); raise SystemExit
м = re.search(r'\n\s*@obzvon\s+path\s', т)
if not м:
    print('блок handle /obzvon не найден — не с чего брать место')
    for с in т.splitlines():
        if 'obzvon' in с:
            print('   строка:', с[:100])
    raise SystemExit
вставка = м.start() + 1
новый = т[:вставка] + БЛОК.lstrip('\n') + т[вставка:]

врем = ФАЙЛ + '.proba'
io.open(врем, 'w', encoding='utf-8').write(новый)
try:
    п = subprocess.run([CADDY, 'validate', '--config', врем, '--adapter', 'caddyfile'],
                       capture_output=True, text=True, timeout=90)
    ок = п.returncode == 0
    print('caddy validate:', 'ПРОШЛА' if ок else f'ПРОВАЛ rc={п.returncode}')
    if not ок:
        print((п.stderr or п.stdout or '')[-400:])
except Exception as e:
    ок = False
    print('validate не запустилась:', type(e).__name__, str(e)[:80])

if not ок:
    os.remove(врем)
    print('НЕ СТАВЛЮ — проверка не пройдена')
    raise SystemExit
if not ПРИМЕНИТЬ:
    os.remove(врем)
    print('СУХОЙ ПРОГОН: проверка пройдена, но файл не заменён')
    raise SystemExit

бэкап = ФАЙЛ + '.bak-' + time.strftime('%Y%m%d-%H%M%S')
shutil.copy2(ФАЙЛ, бэкап)
shutil.move(врем, ФАЙЛ)
print('прежний сохранён:', os.path.basename(бэкап))
п = subprocess.run([CADDY, 'reload', '--config', ФАЙЛ, '--adapter', 'caddyfile'],
                   capture_output=True, text=True, timeout=120)
print('caddy reload rc =', п.returncode, (п.stderr or '')[-200:])
if п.returncode:
    shutil.copy2(бэкап, ФАЙЛ)
    subprocess.run([CADDY, 'reload', '--config', ФАЙЛ, '--adapter', 'caddyfile'],
                   capture_output=True, timeout=120)
    print('ОТКАТ: вернул прежний конфиг')
