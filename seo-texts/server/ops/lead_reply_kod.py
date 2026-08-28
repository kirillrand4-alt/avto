# -*- coding: utf-8 -*-
import io
т = io.open(r"C:\sender\sender\api\app.py", encoding="utf-8", errors="replace").read()
i = т.rfind("def lead_reply", 0, т.find('"incoming"', т.find("def lead_reply")))
j = т.find("\n    @app.", i)
print(т[i - 400:j if j > 0 else i + 2600][:3000])
