# -*- coding: utf-8 -*-
"""Запустить судью доменов ОТВЯЗАННЫМ процессом: раннер режет задания по 30
минут, а суд на 3840 привязок идёт около часа. DETACHED_PROCESS переживает
и таймаут раннера, и рестарт песочницы."""
import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')
СКРИПТ = r'C:\sender\server\prigovor_domenov.py'
ЛОГ = r'C:\sender\server\prigovor-domenov.log'
ф = open(ЛОГ, 'a', encoding='utf-8')
окружение = dict(os.environ)
# решение владельца 17.08 «суди 346 хайкой»: боевую очередь судим дешёвой моделью
окружение.setdefault('PRIGOVOR_MODEL', 'claude-haiku-4-5')
p = subprocess.Popen([sys.executable, СКРИПТ, '--sudit', '10'],
                     stdout=ф, stderr=subprocess.STDOUT,
                     cwd=r'C:\sender\server', env=окружение,
                     creationflags=(subprocess.DETACHED_PROCESS
                                    | subprocess.CREATE_NEW_PROCESS_GROUP))
print(json.dumps({'pid': p.pid, 'лог': ЛОГ}, ensure_ascii=False))
