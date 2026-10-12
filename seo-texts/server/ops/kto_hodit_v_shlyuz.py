# -*- coding: utf-8 -*-
"""Кто сейчас ходит в шлюз: процессы python с соединениями к router.cheap."""
import socket
import subprocess
from collections import Counter

шлюз = set()
try:
    шлюз = {a[4][0] for a in socket.getaddrinfo("router.cheap", 443)}
except Exception:  # noqa: BLE001
    pass
шлюз |= {"104.21.64.2", "172.67.170.163"}
н = subprocess.run(["netstat", "-ano"], capture_output=True, text=True).stdout
по_pid = Counter()
for с in н.splitlines():
    ч = с.split()
    if len(ч) >= 5 and any(ip in ч[2] for ip in шлюз) and ч[3] == "ESTABLISHED":
        по_pid[ч[-1]] += 1
в = subprocess.run(["wmic", "process", "get", "ProcessId,Name,CommandLine"],
                   capture_output=True, text=True).stdout
строки = {}
for с in в.splitlines():
    ч = с.strip().split()
    if ч and ч[-1].isdigit():
        строки[ч[-1]] = " ".join(ч[:-1])
print("соединений со шлюзом по процессам:")
for pid, n in по_pid.most_common():
    print("   pid %-7s %3d  %s" % (pid, n, строки.get(pid, "?")[:150]))
print("")
print("все python-процессы:")
for pid, к in строки.items():
    if "python" in к.lower():
        print("   pid %-7s %s" % (pid, к[:160]))
print("=== КТО ХОДИТ В ШЛЮЗ ===")
