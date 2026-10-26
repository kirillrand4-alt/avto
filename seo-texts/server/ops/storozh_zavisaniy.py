# -*- coding: utf-8 -*-
"""Сторож зависаний автоотправки (26.10: служба дважды вставала на проходе —
письма висят в 'sending', отправок нет). Раз в 3 минуты: есть письмо, взятое
ПОСЛЕ старта сторожа и висящее в 'sending' дольше 12 минут, — снимаем стек
службы (stek_sluzhby.py, py-spy dump) не чаще раза в час и пишем в лог.
Ничего не меняет и службу не перезапускает. Стоп — файл _ops/storozh-zavisaniy.STOP.
    storozh_zavisaniy.py --zapusk"""
import io
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta

ЛОГ = r"C:\sender\_ops\storozh-zavisaniy.log"
СТОП = r"C:\sender\_ops\storozh-zavisaniy.STOP"
if "--zapusk" in sys.argv:
    л = io.open(ЛОГ, "a", encoding="utf-8")
    п = subprocess.Popen([sys.executable, "-u", os.path.abspath(__file__), "--rabota"], cwd=r"C:\sender",
                         stdout=л, stderr=л, creationflags=0x00000008 | 0x00000200)
    time.sleep(5)
    print("сторож запущен, pid %d, жив %s" % (п.pid, п.poll() is None))
    sys.exit(0)
старт = datetime.utcnow().isoformat()
последний_снимок = 0.0
print(time.strftime("%Y-%m-%d %H:%M:%S"), "сторож старт", flush=True)
while not os.path.exists(СТОП):
    try:
        c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
        порог = (datetime.utcnow() - timedelta(minutes=12)).isoformat()
        висят = c.execute("SELECT COUNT(*), MIN(claimed_at) FROM messages WHERE status='sending' AND claimed_at>? AND claimed_at<?",
                          (старт, порог)).fetchone()
        c.close()
        if висят[0] and time.time() - последний_снимок > 3600:
            print(time.strftime("%Y-%m-%d %H:%M:%S"), "ЗАВИСАНИЕ: в sending %d писем с %s — снимаю стек" % висят, flush=True)
            р = subprocess.run([sys.executable, r"C:\sender\server\ops\stek_sluzhby.py"], capture_output=True, text=True,
                               errors="replace", timeout=300)
            print((р.stdout or р.stderr)[:3000], flush=True)
            последний_снимок = time.time()
    except Exception as ex:  # noqa: BLE001
        print(time.strftime("%H:%M:%S"), "сбой проверки:", str(ex)[:200], flush=True)
    time.sleep(180)
print(time.strftime("%Y-%m-%d %H:%M:%S"), "сторож стоп", flush=True)
