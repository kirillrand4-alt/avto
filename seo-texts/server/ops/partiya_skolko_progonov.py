# -*- coding: utf-8 -*-
"""Сколько прогонов генерации живо на сервере. Ничего не трогаем."""
import subprocess

out = subprocess.run(["wmic", "process", "where", "name='python.exe'",
                      "get", "ProcessId,CommandLine"],
                     capture_output=True, text=True, timeout=40).stdout
пиды = [l.split()[-1] for l in out.splitlines()
        if "_gen_partiya" in l and l.split() and l.split()[-1].isdigit()]
print("прогонов:", len(пиды), пиды)
