# -*- coding: utf-8 -*-
import io, os
П = r"C:\sender\sender\lid_stranica.py"
т = io.open(П, encoding="utf-8").read()
print("РАЗМЕР %d знаков, %d строк" % (len(т), t_ := len(т.split("\n"))))
print("=" * 20 + " НАЧАЛО " + "=" * 20)
print(т)
print("=" * 20 + " КОНЕЦ " + "=" * 20)
# кто зовёт
import subprocess  # noqa: F401
for корень in (r"C:\sender\sender",):
    for путь, кат, файлы in os.walk(корень):
        кат[:] = [d for d in кат if d not in ("node_modules", "__pycache__", "web")]
        for имя in файлы:
            if имя.endswith(".py") and имя != "lid_stranica.py":
                p = os.path.join(путь, имя)
                s = io.open(p, encoding="utf-8", errors="ignore").read()
                if "lid_stranica" in s:
                    for i, ln in enumerate(s.split("\n")):
                        if "lid_stranica" in ln:
                            print("ЗОВЁТ %s:%d| %s" % (p, i + 1, ln.strip()[:140]))
