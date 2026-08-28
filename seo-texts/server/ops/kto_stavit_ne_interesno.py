# -*- coding: utf-8 -*-
import io, os, re
корень = r"C:\sender\sender"
for кор, _, файлы in os.walk(корень):
    if "node_modules" in кор or ".git" in кор or "tests" in кор:
        continue
    for ф in файлы:
        if not ф.endswith(".py") or ".bak" in ф:
            continue
        п = os.path.join(кор, ф)
        try:
            т = io.open(п, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        for м in re.finditer(r"not_interested", т):
            стр = т[:м.start()].count("\n") + 1
            строка = т.splitlines()[стр - 1].strip()
            if "set_status" in строка or "status=" in строка or "статус" in строка \
                    or "->" in строка or "lead" in строка.lower():
                print("%-22s %4d  %s" % (os.path.relpath(п, корень), стр, строка[:96]))
