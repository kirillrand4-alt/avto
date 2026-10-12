# -*- coding: utf-8 -*-
"""Полностью показать блокирующие исходящие правила codex_sandbox_*."""
import subprocess

в = subprocess.run(["netsh", "advfirewall", "firewall", "show", "rule",
                    "name=all", "dir=out", "verbose"],
                   capture_output=True, text=True, encoding="cp866",
                   errors="replace").stdout
for б in в.split("\n\n"):
    if "codex" in б.lower():
        print("--- правило ---")
        for с in б.splitlines():
            с = с.strip()
            if с and not с.startswith("---"):
                print("   " + с[:150])
print("=== ПРАВИЛА CODEX ===")
