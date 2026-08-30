# -*- coding: utf-8 -*-
import io, os, re
т = io.open(r"C:\seostat\Parser2\scripts\daily_collect.py", encoding="utf-8",
            errors="ignore").read()
print("=== аргументы daily_collect.py ===")
for м in re.finditer(r"add_argument\(\s*([^)]{0,180})\)", т, re.S):
    print("   %s" % " ".join(м.group(1).split())[:150])
print("\n=== что делает (первые строки докстроки) ===")
д = re.findall(r'"""(.{0,700}?)"""', т, re.S)
if д:
    print(д[0][:700])
print("\n=== serve.py (веб) ===")
s = r"C:\seostat\Parser2\serve.py"
if os.path.exists(s):
    print(io.open(s, encoding="utf-8", errors="ignore").read()[:900])
print("\n=== data/ ===")
d = r"C:\seostat\Parser2\data"
for имя in sorted(os.listdir(d))[:22]:
    п = os.path.join(d, имя)
    if os.path.isfile(п):
        print("   %-28s %10d б" % (имя, os.path.getsize(п)))
