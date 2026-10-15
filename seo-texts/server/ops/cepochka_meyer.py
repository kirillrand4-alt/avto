# -*- coding: utf-8 -*-
"""Цепочка порций Meyer по 400 (владелец 15.10): ждёт конца текущей генерации
(pid в gen-rossiya-9000.pid), затем по очереди запускает zapusk_9000.py на
spisok-meyer-9000-ch1.json, ch2, ... Сам запускается отсоединённым:
    cepochka_meyer.py start   — отсоединиться и работать в фоне
Журнал — _ops\\cepochka-meyer.log."""
import glob, io, os, subprocess, sys, time
ЛОГ = r"C:\sender\_ops\cepochka-meyer.log"
def лог(s):
    with io.open(ЛОГ, "a", encoding="utf-8") as f: f.write(time.strftime("%d.%m %H:%M:%S ") + s + "\n")
if sys.argv[1:] == ["start"]:
    п = subprocess.Popen([sys.executable, __file__, "run"], cwd=r"C:\sender", creationflags=0x00000008 | 0x00000200)
    io.open(r"C:\sender\_ops\cepochka-meyer.pid", "w").write(str(п.pid)); print("цепочка pid", п.pid); sys.exit()
def жив(pid):
    out = subprocess.run(["tasklist", "/FI", "PID eq %s" % pid], capture_output=True, text=True, errors="replace").stdout
    return str(pid) in out
def ждать():
    while True:
        try: pid = io.open(r"C:\sender\_ops\gen-rossiya-9000.pid").read().strip()
        except Exception: return
        if not жив(pid): return
        time.sleep(120)
порции = sorted(glob.glob(r"C:\sender\_ops\spisok-meyer-9000-ch*.json"), key=lambda p: int(p.split("-ch")[1].split(".")[0]))
лог("старт, порций %d" % len(порции))
for п in порции:
    ждать()
    лог("запуск " + п)
    r = subprocess.run([sys.executable, r"C:\sender\server\ops\zapusk_9000.py", "400", "claude-sonnet-4-6", "6", "1.5",
                        "bez-zacepki,peremeshat", "okno=40;byudzhet=250;spisok=" + п], capture_output=True, text=True, errors="replace")
    лог((r.stdout or "")[-300:].replace("\n", " | "))
    time.sleep(60)
ждать(); лог("цепочка закончена")
