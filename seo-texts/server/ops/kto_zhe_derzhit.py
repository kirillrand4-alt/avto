# -*- coding: utf-8 -*-
"""Найти держателя пишущего замка методом исключения.

Снимаем СВОЮ заливку и пробуем взять замок. Если взялся — держала она.
Если нет — держит кто-то из демонов, и тогда смотрим, кто из них пишет
прямо сейчас (по приросту процессорного времени).
"""
import sqlite3
import subprocess
import time

БАЗА = r"C:\sender\enrich.db"


def пш(ком):
    return subprocess.run(["powershell", "-NoProfile", "-Command", ком],
                          capture_output=True, text=True, timeout=90).stdout.strip()


def проба(терпение=25):
    t0 = time.time()
    try:
        c = sqlite3.connect(БАЗА, timeout=терпение, isolation_level=None)
        c.execute("PRAGMA busy_timeout = %d" % (терпение * 1000))
        c.execute("BEGIN IMMEDIATE")
        c.execute("ROLLBACK")
        c.close()
        return "ВЗЯТ за %.2f с" % (time.time() - t0)
    except Exception as ex:                                    # noqa: BLE001
        return "не взят за %.2f с (%s)" % (time.time() - t0, str(ex)[:40])


def цпу():
    вых = пш("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
             "ForEach-Object { \"$($_.ProcessId)=$([int]("
             "($_.UserModeTime + $_.KernelModeTime)/10000000))\" }")
    д = {}
    for с in вых.split():
        if "=" in с:
            п, в = с.split("=", 1)
            try:
                д[п] = int(в)
            except ValueError:
                pass
    return д


до_снятия = проба(10)

мои = пш("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
         "Where-Object { $_.CommandLine -like '*zalit_kody*' } | "
         "ForEach-Object { $_.ProcessId }").split()
for пид in мои:
    if пид.isdigit():
        пш("Stop-Process -Id %s -Force" % пид)
time.sleep(4)
после_снятия = проба(25)

# кто жжёт процессор — тот и работает с базой
ц1 = цпу()
time.sleep(20)
ц2 = цпу()
имена = пш("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
           "ForEach-Object { \"$($_.ProcessId)|\" + "
           "$_.CommandLine.Substring(0,[Math]::Min(74,$_.CommandLine.Length)) }")
имя_по_пиду = {}
for с in (имена or "").splitlines():
    if "|" in с:
        п, к = с.split("|", 1)
        имя_по_пиду[п.strip()] = к.strip()

прирост = sorted(((ц2.get(п, 0) - ц1.get(п, 0), п) for п in ц2),
                 reverse=True)

print("=" * 68)
print("=== СВОДКА: КТО ДЕРЖИТ ПИШУЩИЙ ЗАМОК ===")
print("сейчас: %s" % time.strftime("%d.%m %H:%M:%S"))
print("")
print("замок ДО снятия моей заливки:    %s" % до_снятия)
print("снято моих процессов: %s" % (", ".join(мои) if мои else "не было"))
print("замок ПОСЛЕ снятия моей заливки: %s" % после_снятия)
print("")
print("процессорное время за 20 секунд (кто реально работает):")
for д, п in прирост[:8]:
    if д <= 0:
        continue
    print("   %-8s +%3d с  %s" % (п, д, имя_по_пиду.get(п, "?")[:80]))
if not any(д > 0 for д, _ in прирост):
    print("   никто заметно не грузит процессор")
