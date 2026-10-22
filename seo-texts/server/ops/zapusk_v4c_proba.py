# -*- coding: utf-8 -*-
"""Пробные письма Meyer по ярусу C файла FSA-MEYER-v4 (группа «ФСА v4 C проба», кампания 18; владелец 22.10: «штук 10 писем сделай … посмотрю насколько хороши»).

partiya_gen — драйвер с учётом цены каждого письма и заслоном по цене
(стоп, если годное письмо в окне из 10 попыток дороже порога). Запускаем
отсоединённым процессом, аргументы латиницей (кириллические ключи бьются
при запуске на сервере).

    zapusk_9000.py <сколько писем> <модель> [потоков] [порог]
"""
import io
import os
import subprocess
import sys
import time

сколько = sys.argv[1] if len(sys.argv) > 1 else "12"
модель = sys.argv[2] if len(sys.argv) > 2 else "claude-opus-4-8"
потоков = sys.argv[3] if len(sys.argv) > 3 else "4"
порог = sys.argv[4] if len(sys.argv) > 4 else "1.50"
# Флаги драйвера одним аргументом через запятую, например «bez-predklassa»:
# направление у партии уже задано (Meyer), предклассификатор направления
# здесь лишний, а его последовательные пачки стопорят всё на подвисших
# вызовах шлюза (таймаут ожидания 600 с).
флаги = ["--" + ф.strip() for ф in (sys.argv[5] if len(sys.argv) > 5 else "").split(",") if ф.strip()]
# Именованные аргументы драйвера (6-й аргумент, через ТОЧКУ С ЗАПЯТОЙ —
# запятая нужна внутри значений), например
# «predklass_segment=plastik,metallurgiya».
доп_арг = [а.strip() for а in (sys.argv[6] if len(sys.argv) > 6 else "").split(";") if "=" in а]
журнал = r"C:\sender\_ops\gen-v4c-proba.jsonl"
лог = r"C:\sender\_ops\gen-v4c-proba.log"
арг = [sys.executable, r"C:\sender\server\ops\partiya_gen.py",
       сколько, "10800", "meyer", "0",
       "gruppa=ФСА v4 C проба", "camp_meyer=18", "zhurnal=" + журнал,
       "threads=" + потоков,
       "revenue=0", "model=" + модель, "porog=" + порог] + доп_арг + флаги
ф = io.open(лог, "a", encoding="utf-8")
ф.write("\n==== ЗАПУСК %s: %s писем, %s, потоков %s, порог %s, флаги %s ====\n"
        % (time.strftime("%H:%M:%S"), сколько, модель, потоков, порог, флаги))
ф.flush()
# Канал Claude Kiro включает рассуждение на любом поле thinking — не шлём
# его вовсе (опыт 12.10: 870 токенов с рассуждением против 52-290 без).
окр = dict(os.environ, PROVIDER_THINKING_FIELD="omit")
п = subprocess.Popen(арг, cwd=r"C:\sender", stdout=ф, stderr=ф, env=окр,
                     creationflags=0x00000008 | 0x00000200)
io.open(r"C:\sender\_ops\gen-v4c-proba.pid", "w").write(str(п.pid))
time.sleep(20)
print("pid %d жив: %s" % (п.pid, п.poll() is None))
т = io.open(лог, encoding="utf-8", errors="replace").read()
print(т[-1500:])
print("=== ЗАПУСК ФСА V4 C ПРОБА ===")
