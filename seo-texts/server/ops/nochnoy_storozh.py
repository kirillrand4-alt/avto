# -*- coding: utf-8 -*-
"""Ночной сторож: ждёт, пока у шлюза оживёт СТРИМ, и пускает блок сам.

31.08 вечером шлюз перестал отдавать стрим: короткий вызов идёт 90 секунд,
вызов с system падает «стрим молчит 102с». Весь конвейер работает только
стримом, поэтому генерация невозможна. Ждать вручную бессмысленно, поэтому
проверяем раз в 20 минут одним коротким вызовом (это копейки) и, как только
он пройдёт быстрее порога, запускаем ночной блок и выходим.

Запускать отцепленно: python pl_run.py pustit_otceplenno.py nochnoy_storozh.py
"""
import io
import os
import subprocess
import sys
import time

sys.path.insert(0, r"C:\sender")
import gen_provider                                           # noqa: E402

ПОРОГ_СЕК = 20.0          # быстрее этого — считаем, что стрим ожил
ПАУЗА = 1200              # 20 минут между пробами
ПРЕДЕЛ_ЧАСОВ = 10
ЖУРНАЛ = r"C:\sender\_ops\nochnoy-storozh.log"
КОМАНДА = ["partiya_gen.py", "1500", "25200", "meyer", "1",
           "модель=claude-sonnet-4-6", "--bez-predklassa"]


def запись(с):
    строка = "%s %s" % (time.strftime("%d.%m %H:%M:%S"), с)
    print(строка)
    with io.open(ЖУРНАЛ, "a", encoding="utf-8") as f:
        f.write(строка + "\n")
        f.flush()
        os.fsync(f.fileno())


def стрим_жив():
    т0 = time.time()
    try:
        m = gen_provider._raw_stream(
            [{"role": "user", "content": "ответь одним словом: готов"}],
            "claude-sonnet-4-6", 200, thinking=False,
            system="Отвечай одним словом.")
        текст = "".join(getattr(b, "text", "")
                        for b in getattr(m, "content", []) or [])
        сек = time.time() - т0
        return (сек <= ПОРОГ_СЕК and bool(текст)), сек, текст[:40]
    except Exception as e:                                    # noqa: BLE001
        return False, time.time() - т0, str(e)[:80]


запись("сторож пущен, порог %.0f с, пауза %d с" % (ПОРОГ_СЕК, ПАУЗА))
т_старта = time.time()
круг = 0
while time.time() - т_старта < ПРЕДЕЛ_ЧАСОВ * 3600:
    круг += 1
    ок, сек, что = стрим_жив()
    запись("круг %d: стрим %s за %.1f с — %s"
           % (круг, "ЖИВ" if ок else "молчит", сек, что))
    if ок:
        r = subprocess.run(["powershell", "-NoProfile", "-Command",
                            "(Get-CimInstance Win32_Process -Filter "
                            "\"Name like 'python%'\" | Where-Object "
                            "{ $_.CommandLine -like '*partiya_gen*' }).Count"],
                           capture_output=True, text=True, timeout=90)
        if (r.stdout or "").strip() not in ("", "0"):
            запись("блок уже идёт — сторожу делать нечего, выхожу")
            break
        путь = os.path.join(r"C:\sender\_ops", KOMANDA_0 := КОМАНДА[0])
        метка = time.strftime("%m%d-%H%M%S")
        основа = os.path.join(r"C:\sender\_ops",
                              "partiya_gen-%s" % метка)
        арг = [путь] + КОМАНДА[1:]
        список = ", ".join("'" + a.replace("'", "''") + "'" for a in арг)
        ком = ("$env:PYTHONIOENCODING='utf-8'; Start-Process -FilePath "
               "'C:\\Program Files\\Python311\\python.exe' -ArgumentList %s "
               "-WindowStyle Hidden -RedirectStandardOutput '%s.log' "
               "-RedirectStandardError '%s.err'" % (список, основа, основа))
        subprocess.run(["powershell", "-NoProfile", "-Command", ком],
                       timeout=90)
        запись("СТРИМ ОЖИЛ — блок запущен, лог %s.log" % основа)
        break
    time.sleep(ПАУЗА)
else:
    запись("предел %d часов исчерпан, стрим так и не ожил" % ПРЕДЕЛ_ЧАСОВ)
запись("сторож завершил работу")
