# -*- coding: utf-8 -*-
import io
т = io.open(r"C:\sender\sender\probe_enrich.py", encoding="utf-8", errors="replace").read()
i = т.index("def записать")
print(т[i:i + 2200])
