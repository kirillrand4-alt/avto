# -*- coding: utf-8 -*-
"""Что сделала соседняя сессия с обработкой отказа — читаем целиком.

Мой патч не встал: якорь занят её правкой. Каталог C:\\sender\\sender
общий, и заливать своё поверх чужого нельзя — 17.08 так уже разъехались
две выкатки. Сначала читаем, что там есть, и только потом решаем, нужно
ли вообще что-то трогать.

Заодно смотрим время правки файла: если она легла ПОСЛЕ перезапуска
панели, панель работает на старом коде, и отказы всё ещё теряются.
"""
import io
import os
import subprocess
import time

путь = r"C:\sender\sender\imap_watcher.py"
строки = io.open(путь, encoding="utf-8").read().splitlines()

print("файл изменён %d секунд назад (%s)"
      % (int(time.time() - os.path.getmtime(путь)),
         time.strftime("%H:%M:%S", time.localtime(os.path.getmtime(путь)))))

н = next((и for и, с in enumerate(строки)
          if 'signal.kind == "not_interested"' in с), None)
if н is None:
    print("строки с not_interested нет вовсе")
else:
    print("\n=== БЛОК ОБРАБОТКИ ОТКАЗА, СТРОКИ %d-%d ===" % (н + 1, н + 40))
    for к in range(н, min(н + 40, len(строки))):
        print("%5d| %s" % (к + 1, строки[к]))

print("\n=== КОГДА ПАНЕЛЬ ПОСЛЕДНИЙ РАЗ СТАРТОВАЛА ===")
try:
    cmd = ('powershell -NoProfile -ExecutionPolicy Bypass -Command '
           '"$p=Get-CimInstance Win32_Service -Filter \\"Name=\'SenderPanel\'\\"; '
           '$q=Get-CimInstance Win32_Process -Filter (\'ProcessId=\'+$p.ProcessId); '
           '$q.CreationDate.ToString(\'HH:mm:ss\')"')
    p = subprocess.run(cmd, shell=True, capture_output=True, timeout=60)
    print("  процесс панели запущен в: %s"
          % ((p.stdout or b"").decode("cp866", "replace").strip() or "?"))
except Exception as e:                                         # noqa: BLE001
    print("  не определилось:", str(e)[:80])

print("\n=== КОПИИ ФАЙЛА (кто и когда правил) ===")
кат = os.path.dirname(путь)
for имя in sorted(os.listdir(кат)):
    if имя.startswith("imap_watcher.py.bak"):
        п = os.path.join(кат, имя)
        print("  %-44s %s  %d байт"
              % (имя, time.strftime("%H:%M:%S",
                                    time.localtime(os.path.getmtime(п))),
                 os.path.getsize(п)))
