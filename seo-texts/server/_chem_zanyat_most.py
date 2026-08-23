# -*- coding: utf-8 -*-
r"""Чем занят мост: процессорное время и чтение с диска за 20 секунд."""
import json
import subprocess
import time


def снять():
    o = subprocess.run(
        ['powershell', '-NoProfile', '-Command',
         "Get-CimInstance Win32_Process -Filter \"ProcessId=300240\" | "
         "%{ '{0}|{1}|{2}' -f $_.KernelModeTime, $_.UserModeTime, $_.ReadOperationCount }"],
        capture_output=True, text=True, timeout=90)
    return (o.stdout or '').strip()


a = снять()
time.sleep(20)
b = снять()
d = {'было': a, 'стало': b}
if a and b:
    ч1 = [int(x) for x in a.split('|')]
    ч2 = [int(x) for x in b.split('|')]
    d['цп_секунд_за_20с'] = round((ч2[0] + ч2[1] - ч1[0] - ч1[1]) / 1e7, 2)
    d['чтений_за_20с'] = ч2[2] - ч1[2]
print(json.dumps(d, ensure_ascii=False, indent=1))
