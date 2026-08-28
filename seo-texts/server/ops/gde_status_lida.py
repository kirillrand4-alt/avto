# -*- coding: utf-8 -*-
import io, os, re
корень = r"C:\sender\sender"
нашли = []
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
        for м in re.finditer(r"(status_changed|lead_set_status|set_lead_status|"
                             r"def lead_status|reply_kind_recheck)", т):
            стр = т[:м.start()].count("\n") + 1
            нашли.append((os.path.relpath(п, корень), стр,
                          т.splitlines()[стр - 1].strip()[:96]))
for f, s, l in нашли[:20]:
    print("%-22s %4d  %s" % (f, s, l))
