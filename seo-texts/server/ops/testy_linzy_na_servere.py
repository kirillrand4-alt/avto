# -*- coding: utf-8 -*-
"""Прогон тестов автоснятия на выкаченном коде."""
import subprocess
import sys
r = subprocess.run([sys.executable, "-m", "pytest",
                    r"C:\sender\sender\tests\test_linza_snimaet_sama.py",
                    r"C:\sender\sender\tests\test_formulirovki_meyer.py",
                    r"C:\sender\sender\tests\test_regionalnoe_chislo.py", "-q"],
                   capture_output=True, text=True, cwd=r"C:\sender")
print(r.stdout[-1500:])
print(r.stderr[-400:])
