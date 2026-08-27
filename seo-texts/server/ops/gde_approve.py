# -*- coding: utf-8 -*-
import io, os, re
корень = r"C:\sender\sender"
найдено = []
for кор, _, файлы in os.walk(корень):
    if "node_modules" in кор or "\\.git" in кор:
        continue
    for ф in файлы:
        if not ф.endswith(".py") or ".bak" in ф:
            continue
        п = os.path.join(кор, ф)
        try:
            т = io.open(п, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        for м in re.finditer(r"(?m)^.*(approve|confirm_list|route|@app\.|add_url_rule|do_POST).*$", т):
            s = м.group(0).strip()
            if "approve" in s and ("def " in s or "/" in s or "path" in s.lower()):
                найдено.append("%s: %s" % (os.path.relpath(п, корень), s[:120]))
for с in найдено[:40]:
    print(с)
print("---")
print("файлы верхнего уровня:", ", ".join(sorted(
    f for f in os.listdir(корень) if f.endswith(".py") and ".bak" not in f))[:900])
