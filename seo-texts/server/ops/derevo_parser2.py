# -*- coding: utf-8 -*-
import io, os, re
корень = r"C:\seostat\Parser2"
for путь, кат, файлы in os.walk(корень):
    кат[:] = [d for d in кат if d not in ("__pycache__", ".venv", "venv",
                                          ".git", "node_modules")]
    ур = путь.replace(корень, "").count(os.sep)
    if ур > 2:
        continue
    print("%s%s/" % ("  " * ур, os.path.basename(путь) or "Parser2"))
    for имя in sorted(файлы):
        if имя.endswith((".py", ".md", ".txt", ".cfg", ".toml", ".json")):
            п = os.path.join(путь, имя)
            р = os.path.getsize(п)
            подпись = ""
            if имя.endswith(".py") and р < 200000:
                т = io.open(п, encoding="utf-8", errors="ignore").read()
                д = re.findall(r'"""(.{0,110}?)"""', т, re.S)
                if д:
                    подпись = " — " + " ".join(д[0].split())[:88]
            print("%s  %-34s %7d%s" % ("  " * ур, имя, р, подпись))
