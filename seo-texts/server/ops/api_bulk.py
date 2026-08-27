# -*- coding: utf-8 -*-
import io, re
т = io.open(r"C:\sender\sender\api\app.py", encoding="utf-8", errors="replace").read()
print("строк в api/app.py: %d" % t.count("\n") if False else "строк: %d" % т.count("\n"))
for м in re.finditer(r"(?m)^@?(app\.|router\.)?(get|post|put|delete|route)\(.*$", т):
    s = м.group(0).strip()
    if "confirm" in s or "approve" in s or "batch" in s or "bulk" in s:
        print("   " + s[:120])
print("--- окрестности массового approve ---")
i = т.find("те же заслоны, что одиночный approve")
if i > 0:
    print(т[max(0, i - 2200):i + 1800])
