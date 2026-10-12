# -*- coding: utf-8 -*-
"""Что делает процесс генерации: соединения наружу, CPU, потоки."""
import io
import socket
import subprocess
import time

pid = io.open(r"C:\sender\_ops\gen-rossiya-9000.pid").read().strip()
шлюз = set()
try:
    шлюз = {a[4][0] for a in socket.getaddrinfo("router.cheap", 443)}
except Exception:  # noqa: BLE001
    pass
н = subprocess.run(["netstat", "-ano"], capture_output=True, text=True).stdout
свои = [с for с in н.splitlines() if с.strip().endswith(" " + pid)]
к_шлюзу = [с for с in свои if any(ip in с for ip in шлюз)]
print("pid %s: соединений всего %d, к шлюзу %d (ESTABLISHED %d)"
      % (pid, len(свои), len(к_шлюзу), sum("ESTABLISHED" in с for с in к_шлюзу)))
for с in свои[:8]:
    print("   " + " ".join(с.split()))
в = subprocess.run(["wmic", "process", "where", "ProcessId=%s" % pid, "get",
                    "KernelModeTime,UserModeTime,ThreadCount,WorkingSetSize"],
                   capture_output=True, text=True).stdout
print(" ".join(в.split()))
time.sleep(10)
в2 = subprocess.run(["wmic", "process", "where", "ProcessId=%s" % pid, "get",
                     "UserModeTime"], capture_output=True, text=True).stdout
print("через 10 с: " + " ".join(в2.split()))
print("=== ПРОЦЕСС ===")
