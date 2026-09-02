# -*- coding: utf-8 -*-
"""Только чтение: как служба создаёт Sender с индексом обзвона."""
import io
import os
import re

print("=== ГДЕ СОЗДАЁТСЯ Sender( ===")
for корень in (r"C:\sender\sender", r"C:\sender\server", r"C:\sender"):
    if not os.path.isdir(корень):
        continue
    for дп, _, фс in os.walk(корень):
        if "tests" in дп or "ops" in дп:
            continue
        for ф in фс:
            if not ф.endswith(".py"):
                continue
            п = os.path.join(дп, ф)
            т = io.open(п, encoding="utf-8", errors="replace").read()
            лн = т.splitlines()
            for м in re.finditer(r"Sender\(", т):
                н = т[:м.start()].count("\n")
                кусок = " ".join(x.strip() for x in лн[н:н + 4])
                print("  %s:%d  %s" % (os.path.relpath(п, r"C:\sender"), н + 1,
                                       кусок[:150]))

print("\n=== ГДЕ СОЗДАЁТСЯ cards / индекс обзвона ===")
for корень in (r"C:\sender\sender",):
    for дп, _, фс in os.walk(корень):
        if "tests" in дп:
            continue
        for ф in фс:
            if not ф.endswith(".py"):
                continue
            п = os.path.join(дп, ф)
            т = io.open(п, encoding="utf-8", errors="replace").read()
            лн = т.splitlines()
            for м in re.finditer(r"(cards\s*=|def cards|class .*Cards|obzvon)", т):
                н = т[:м.start()].count("\n")
                с = лн[н].strip()
                if с.startswith("#"):
                    continue
                print("  %s:%d  %s" % (ф, н + 1, с[:104]))
