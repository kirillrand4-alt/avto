# -*- coding: utf-8 -*-
"""Только чтение: точный путь рендера письма перед отправкой."""
import inspect
import io
import os
import re
import sys

sys.path.insert(0, r"C:\sender")

print("=== _apply_signature ===")
from sender.sender import Sender  # noqa: E402
print(inspect.getsource(Sender._apply_signature)[:1700])

print("\n=== sender.py 950-985 (что делает render перед отправкой) ===")
т = io.open(r"C:\sender\sender\sender.py", encoding="utf-8", errors="replace").read().splitlines()
for i in range(949, 986):
    print("  %4d| %s" % (i + 1, т[i][:104]))

print("\n=== ГДЕ ИМЯ_ОТПРАВИТЕЛЯ ЗАМЕНЯЕТСЯ (все вхождения вне тестов) ===")
for корень in (r"C:\sender\sender",):
    for дп, _, фс in os.walk(корень):
        if "tests" in дп:
            continue
        for ф in фс:
            if not ф.endswith(".py"):
                continue
            п = os.path.join(дп, ф)
            s = io.open(п, encoding="utf-8", errors="replace").read()
            лн = s.splitlines()
            for м in re.finditer(r"ИМЯ_ОТПРАВИТЕЛЯ", s):
                н = s[:м.start()].count("\n")
                print("  %s:%d  %s" % (ф, н + 1, лн[н].strip()[:100]))
