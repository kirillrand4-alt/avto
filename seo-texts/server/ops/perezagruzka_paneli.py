# -*- coding: utf-8 -*-
"""Перезапуск службы панели силами сессии (владелец разрешил 28.08.2026).

Задание крутится внутри процесса самой службы, поэтому команду отдаём
ОТЦЕПЛЕННОМУ процессу: он переживёт остановку службы и доведёт дело до конца,
а это задание успеет вернуть отчёт.

Перед этим смотрим, не режем ли живое: письма в статусе 'sending' держат
аренду, и остановка посреди отправки оставляет их висеть (так 26.08 залипли
23 штуки — их потом пришлось освобождать руками).
"""
import sqlite3
import subprocess
import sys
import time

КАТИТЬ = "--katit" in sys.argv
БАЗА = r"C:\sender\sender.db"

c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
в_полёте = c.execute("SELECT COUNT(*) FROM messages WHERE status='sending'"
                     ).fetchone()[0]
на_подходе = c.execute(
    "SELECT COUNT(*) FROM messages WHERE status='scheduled' AND scheduled_at <= ?",
    (time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() + 300)),)
).fetchone()[0]
c.close()
print("сейчас в отправке (аренда занята): %d" % в_полёте)
print("уйдёт в ближайшие 5 минут:        %d" % на_подходе)

r = subprocess.run(["sc.exe", "queryex", "SenderPanel"], capture_output=True,
                   text=True, timeout=30)
pid_до = ""
for стр in (r.stdout or "").splitlines():
    if "PID" in стр:
        pid_до = стр.split(":")[-1].strip()
print("PID службы сейчас: %s" % pid_до)

if not КАТИТЬ:
    print("\n[сухой прогон] с --katit отдам команду")
    raise SystemExit(0)

if в_полёте:
    print("\nПисьма в отправке есть — аренда останется занятой, сниму "
          "следующим прогоном.")

команда = ("Start-Sleep -Seconds 4; "
           "Restart-Service SenderPanel -Force; "
           "Start-Sleep -Seconds 8; "
           "(Get-Service SenderPanel).Status | Out-File -Encoding utf8 "
           r"'C:\sender\_ops\perezapusk-itog.txt'")
ОТЦЕПИТЬ = 0x00000008 | 0x00000200        # DETACHED_PROCESS | NEW_PROCESS_GROUP
subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden",
                  "-Command", команда],
                 creationflags=ОТЦЕПИТЬ,
                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                 stderr=subprocess.DEVNULL, close_fds=True)
print("\nкоманда отдана отцепленному процессу, сработает через 4 секунды")
print("PID до: %s — проверю после" % pid_до)
