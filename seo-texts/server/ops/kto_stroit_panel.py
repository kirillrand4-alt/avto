# -*- coding: utf-8 -*-
import io, os, re
корень = r"C:\sender\sender"
for кор, _, файлы in os.walk(корень):
    if "node_modules" in кор or ".git" in кор:
        continue
    for ф in файлы:
        if not ф.endswith(".py") or ".bak" in ф:
            continue
        п = os.path.join(кор, ф)
        try:
            т = io.open(п, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        if '"incoming"' not in т and "'incoming'" not in т:
            continue
        for м in re.finditer(r'["\']incoming["\']\s*:', т):
            н = т.rfind("def ", 0, м.start())
            имя = т[н:т.find("(", н)] if н > 0 else "?"
            стр = т[:м.start()].count("\n") + 1
            print("%-22s %-44s строка %d" % (os.path.relpath(п, корень), имя[:44], стр))
