# -*- coding: utf-8 -*-
"""Сколько python-процессов с подстрокой в командной строке: skolko_processov.py <подстрока>"""
import subprocess, sys
в = subprocess.run(["wmic", "process", "where", "name='python.exe'", "get", "ProcessId,CommandLine"], capture_output=True, text=True).stdout
с = [x.strip()[:160] for x in в.splitlines() if sys.argv[1] in x and "skolko_processov" not in x]
print(len(с)); [print(x) for x in с]
