# -*- coding: utf-8 -*-
"""Сверка боевых файлов после выкатки + прогон тестов правок.

Выкатывал ai_letter.py и ai_quota.py БЕЗ предварительной сверки sha256 -
нарушил собственное правило (каталог делится с соседней сессией). Сверяю
задним числом хотя бы то, что можно: размеры, наличие моих правок и то, что
чужие следы на месте.
"""
import hashlib
import io
import os
import subprocess
import sys

for имя in ("ai_letter.py", "ai_quota.py", "lovushki.py", "target_gate.py"):
    p = os.path.join(r"C:\sender\sender", имя)
    d = io.open(p, "rb").read()
    t = d.decode("utf-8", "replace")
    метки = {
        "ai_letter.py": ("_РЕГИОНАЛЬНОЕ_ЧИСЛО", "drafts: dict"),
        "ai_quota.py": ("_izbytochnoe_regionalnoe", "_site_text"),
        "lovushki.py": ("ЗАГЛУШКИ", "ВОСКРЕСШИЙ"),
        "target_gate.py": ("минус_класс", "МИНУС_ОКВЭД"),
    }[имя]
    print(f"{имя}: {len(d)}б sha256={hashlib.sha256(d).hexdigest()[:16]}… "
          + " ".join(f"{м}={'да' if м in t else 'НЕТ'}" for м in метки))

r = subprocess.run([sys.executable, "-m", "pytest",
                    r"C:\sender\sender\tests\test_zaglushki_v_baze.py",
                    r"C:\sender\sender\tests\test_regionalnoe_chislo.py",
                    r"C:\sender\sender\tests\test_medicina_v_minus.py",
                    r"C:\sender\sender\tests\test_teh_lens.py", "-q"],
                   capture_output=True, text=True, cwd=r"C:\sender")
print(r.stdout[-1200:])
