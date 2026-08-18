# -*- coding: utf-8 -*-
"""Прогнать на сервере тесты минус-класса — там, где живёт боевой код."""
import subprocess
import sys
r = subprocess.run([sys.executable, "-m", "pytest",
                    r"C:\sender\sender\tests\test_medicina_v_minus.py",
                    "-q"],
                   capture_output=True, text=True, cwd=r"C:\sender")
print(r.stdout[-2500:])
print(r.stderr[-800:])
