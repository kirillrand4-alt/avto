# -*- coding: utf-8 -*-
import io, re
т = io.open(r"C:\sender\sender\api\app.py", encoding="utf-8", errors="replace").read()
for м in re.finditer(r"(?m)^\s*from\s+\S+\s+import\s+.*(next_slot|window_from|recipient_tz_name|AutoSend|ENABLED_KEY).*$", т):
    print(м.group(0).strip()[:130])
i = т.find("ENABLED_KEY =")
if i > 0:
    print("---", т[i:i + 120].split("\n")[0])
