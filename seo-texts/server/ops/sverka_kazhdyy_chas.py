# -*- coding: utf-8 -*-
"""Сверку лидов — каждый час, а не раз в сутки.

Ночного прогона мало: 25.08 «Шато де Талю» спросила цену и КП, и такой
вопрос не должен ждать до утра. Прогон дешёвый — один запрос по событиям за
неделю и склейка по адресу, — так что частота ему ничего не стоит.
"""
import subprocess
import sys

ИМЯ = "sender-sverka-lidov"
ОБЁРТКА = r"C:\sender\_ops\sverka-lidov.cmd"
ДЕЛАТЬ = "primenit" in sys.argv[1:]

в = subprocess.run(["schtasks", "/query", "/tn", ИМЯ, "/fo", "LIST"],
                   capture_output=True, timeout=40)
for с in (в.stdout or b"").decode("cp866", "replace").splitlines():
    if с.strip():
        print("   %s" % с.strip())
if not ДЕЛАТЬ:
    print("\nвхолостую. Переставить на час — primenit")
    raise SystemExit(0)

п = subprocess.run(["schtasks", "/create", "/tn", ИМЯ, "/tr", ОБЁРТКА,
                    "/sc", "hourly", "/mo", "1", "/ru", "SYSTEM", "/f"],
                   capture_output=True, timeout=60)
print("\nпересоздание: rc=%s %s"
      % (п.returncode, (п.stdout or п.stderr).decode("cp866", "replace").strip()[:160]))
з = subprocess.run(["schtasks", "/query", "/tn", ИМЯ, "/fo", "LIST"],
                   capture_output=True, timeout=40)
for с in (з.stdout or b"").decode("cp866", "replace").splitlines():
    if с.strip():
        print("   %s" % с.strip())
